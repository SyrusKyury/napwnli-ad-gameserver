import os
import time
import json
import uuid
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait, ALL_COMPLETED
from flask import Flask, request, jsonify, render_template, redirect, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import update, UniqueConstraint

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError("SECRET_KEY environment variable must be set")

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')
MAX_FLAGS_PER_SUBMIT = 50  # batch submit limit

db = SQLAlchemy(app)

# --- STATO IN MEMORIA ---
GAME_STATE = {"tick": 0, "active": False}
RATE_LIMITS = {}
state_lock = threading.Lock()

# Ultimi errori checker: { (team_id, service_id): {team, service, tick, error} }
CHECKER_ERRORS = {}
errors_lock = threading.Lock()


# --- DATABASE MODELS ---

class Config(db.Model):
    key   = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(100))

class Team(db.Model):
    id      = db.Column(db.Integer, primary_key=True)
    name    = db.Column(db.String(50), unique=True)
    ip      = db.Column(db.String(20))
    api_key = db.Column(db.String(64), default=lambda: uuid.uuid4().hex)
    score   = db.Column(db.Float, default=0.0)

class Service(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(50))
    checker_file   = db.Column(db.String(100))
    flags_per_tick = db.Column(db.Integer, default=1)

class Flag(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    flag_string  = db.Column(db.String(64), unique=True, index=True)
    team_id      = db.Column(db.Integer, db.ForeignKey('team.id'))
    service_id   = db.Column(db.Integer, db.ForeignKey('service.id'))
    tick_created = db.Column(db.Integer)
    flag_id      = db.Column(db.String(100))
    secret       = db.Column(db.String(256))
    captured     = db.Column(db.Boolean, default=False)

class CheckerResult(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    team_id    = db.Column(db.Integer, db.ForeignKey('team.id'))
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'))
    tick       = db.Column(db.Integer)
    status     = db.Column(db.String(10))

class TeamServiceScore(db.Model):
    __table_args__ = (UniqueConstraint('team_id', 'service_id'),)
    id           = db.Column(db.Integer, primary_key=True)
    team_id      = db.Column(db.Integer, db.ForeignKey('team.id'))
    service_id   = db.Column(db.Integer, db.ForeignKey('service.id'))
    flags_gained = db.Column(db.Integer, default=0)
    flags_lost   = db.Column(db.Integer, default=0)
    ticks_up     = db.Column(db.Integer, default=0)
    ticks_total  = db.Column(db.Integer, default=0)
    last_status  = db.Column(db.String(10), default='UNKNOWN')
    last_tick    = db.Column(db.Integer, default=0)


# --- CONFIG HELPERS ---

def get_config(key, default):
    row = Config.query.get(key)
    return row.value if row else default

def set_config(key, value):
    row = Config.query.get(key)
    if row:
        row.value = str(value)
    else:
        db.session.add(Config(key=key, value=str(value)))

def get_tick_duration():
    return int(get_config('tick_duration', os.environ.get('TICK_DURATION', 60)))

def get_sla_bonus_k():
    return float(get_config('sla_bonus_k', os.environ.get('SLA_BONUS_K', 5.0)))


# --- GAME HELPERS ---

def get_sla_from_tss(tss):
    """Calcola SLA da contatori in TSS — O(1), nessuna query."""
    if tss is None or tss.ticks_total == 0:
        return 1.0
    return tss.ticks_up / tss.ticks_total

def get_or_create_tss(team_id, service_id):
    tss = TeamServiceScore.query.filter_by(
        team_id=team_id, service_id=service_id
    ).with_for_update().first()
    if not tss:
        tss = TeamServiceScore(team_id=team_id, service_id=service_id)
        db.session.add(tss)
        db.session.flush()
    return tss

def do_reset():
    Flag.query.delete()
    CheckerResult.query.delete()
    TeamServiceScore.query.delete()
    db.session.execute(update(Team).values(score=0.0))
    db.session.commit()
    with state_lock:
        GAME_STATE['tick'] = 0
        GAME_STATE['active'] = False
    RATE_LIMITS.clear()
    with errors_lock:
        CHECKER_ERRORS.clear()

def call_checker(script_path, input_data):
    """Esegue il checker. Se eseguibile lo chiama direttamente, altrimenti usa python."""
    try:
        executable = os.access(script_path, os.X_OK)
        cmd = [script_path] if executable else ['python', script_path]
        res = subprocess.run(
            cmd,
            input=json.dumps(input_data).encode(),
            capture_output=True,
            timeout=10
        )
        out = json.loads(res.stdout.decode('utf-8', errors='ignore') or '{}')
        err = res.stderr.decode('utf-8', errors='ignore')[:200]
        return out, err
    except Exception as e:
        return {'status': 'DOWN'}, str(e)


# --- TICK SCHEDULER ---

def run_checker(team_id, team_ip, service_id, checker_file, tick):
    script_path = os.path.join('checkers', os.path.basename(checker_file))

    # 1. CHECK
    check_out, check_err = call_checker(script_path, {
        'action': 'check', 'ip': team_ip, 'tick': tick
    })
    check_status = check_out.get('status', 'DOWN').upper()

    # 2. PUT
    flag_str = f'NPW_{uuid.uuid4().hex}'
    put_out, put_err = call_checker(script_path, {
        'action': 'put', 'ip': team_ip, 'flag': flag_str, 'tick': tick
    })
    put_status = put_out.get('status', 'DOWN').upper()
    flag_id    = put_out.get('flag_id', '')
    secret     = put_out.get('secret', '')

    # 3. GET
    get_status = 'DOWN'
    get_err    = ''
    if put_status == 'UP' and flag_id:
        get_out, get_err = call_checker(script_path, {
            'action': 'get', 'ip': team_ip,
            'flag_id': flag_id, 'secret': secret, 'flag': flag_str, 'tick': tick
        })
        get_status = get_out.get('status', 'DOWN').upper()

    if check_status == 'UP' and put_status == 'UP' and get_status == 'UP':
        final_status = 'UP'
    elif 'MUMBLE' in (check_status, put_status, get_status):
        final_status = 'MUMBLE'
    else:
        final_status = 'DOWN'

    # Raccoglie errori se il servizio non e' UP
    if final_status != 'UP':
        parts = []
        if check_status != 'UP':
            parts.append(f'check={check_status}' + (f' ({check_err})' if check_err else ''))
        if put_status != 'UP':
            parts.append(f'put={put_status}' + (f' ({put_err})' if put_err else ''))
        if get_status != 'UP' and put_status == 'UP':
            parts.append(f'get={get_status}' + (f' ({get_err})' if get_err else ''))
        error_msg = ' | '.join(parts) or final_status
        with errors_lock:
            CHECKER_ERRORS[(team_id, service_id)] = {
                'tick':  tick,
                'error': error_msg[:300],
            }
    else:
        # Pulisce l'errore precedente se il servizio torna UP
        with errors_lock:
            CHECKER_ERRORS.pop((team_id, service_id), None)

    with app.app_context():
        db.session.add(CheckerResult(
            team_id=team_id, service_id=service_id,
            tick=tick, status=final_status
        ))
        if put_status == 'UP' and flag_id:
            db.session.add(Flag(
                flag_string=flag_str, team_id=team_id, service_id=service_id,
                tick_created=tick, flag_id=flag_id, secret=secret
            ))
        db.session.execute(
            update(TeamServiceScore)
            .where(
                TeamServiceScore.team_id == team_id,
                TeamServiceScore.service_id == service_id
            )
            .values(
                ticks_total=TeamServiceScore.ticks_total + 1,
                ticks_up=TeamServiceScore.ticks_up + (1 if final_status == 'UP' else 0),
                last_status=final_status,
                last_tick=tick
            )
        )
        db.session.commit()

def tick_loop():
    with app.app_context():
        while True:
            # Legge config una volta per tick, non ad ogni iterazione del while
            tick_duration = get_tick_duration()

            if GAME_STATE['active']:
                tick_start = time.time()

                with state_lock:
                    GAME_STATE['tick'] += 1
                tick = GAME_STATE['tick']
                print(f'--- START TICK {tick} ---')

                teams    = [(t.id, t.ip) for t in Team.query.all()]
                services = [(s.id, s.checker_file) for s in Service.query.all()]

                # Pre-crea TSS mancanti nel thread principale per evitare
                # la race condition di get_or_create concorrente nei worker
                for team_id, _ in teams:
                    for service_id, _ in services:
                        exists = TeamServiceScore.query.filter_by(
                            team_id=team_id, service_id=service_id
                        ).first()
                        if not exists:
                            db.session.add(TeamServiceScore(
                                team_id=team_id, service_id=service_id
                            ))
                db.session.commit()

                min_tick = max(0, tick - 5)
                Flag.query.filter(Flag.tick_created < min_tick).delete()
                db.session.commit()

                checker_timeout = max(10, tick_duration - 5)

                with ThreadPoolExecutor(max_workers=20) as executor:
                    futures = [
                        executor.submit(
                            run_checker,
                            team_id, team_ip, service_id, checker_file, tick
                        )
                        for team_id, team_ip in teams
                        for service_id, checker_file in services
                    ]
                    done, not_done = futures_wait(futures, timeout=checker_timeout)
                    if not_done:
                        print(f'WARNING: {len(not_done)} checkers timed out at tick {tick}')

                # Bonus SLA — usa i contatori in TSS, nessuna query aggiuntiva
                sla_bonus_k = get_sla_bonus_k()
                results_this_tick = CheckerResult.query.filter_by(tick=tick).all()
                bonus_map = {}
                for r in results_this_tick:
                    if r.status == 'UP':
                        bonus_map[r.team_id] = bonus_map.get(r.team_id, 0.0) + sla_bonus_k

                for team_id, bonus in bonus_map.items():
                    db.session.execute(
                        update(Team)
                        .where(Team.id == team_id)
                        .values(score=Team.score + bonus)
                    )
                db.session.commit()

                elapsed    = time.time() - tick_start
                sleep_time = max(1, tick_duration - elapsed)
            else:
                sleep_time = tick_duration

            time.sleep(sleep_time)


# --- ROUTES: PUBLIC ---

@app.route('/')
def scoreboard():
    teams    = Team.query.order_by(Team.score.desc()).all()
    services = Service.query.all()

    # Tutto da TSS — due query, nessuno scan di CheckerResult
    all_tss = TeamServiceScore.query.all()
    tss_map = {(r.team_id, r.service_id): r for r in all_tss}

    data = {}
    for t in teams:
        data[t.id] = {}
        for s in services:
            tss = tss_map.get((t.id, s.id))
            data[t.id][s.id] = {
                'status': tss.last_status  if tss else 'UNKNOWN',
                'sla':    round(get_sla_from_tss(tss) * 100, 1),
                'gained': tss.flags_gained if tss else 0,
                'lost':   tss.flags_lost   if tss else 0,
            }

    return render_template('index.html',
                           teams=teams, services=services, data=data,
                           tick=GAME_STATE['tick'], active=GAME_STATE['active'])

@app.route('/rules')
def rules():
    return render_template('rules.html')


# --- ROUTES: AUTH ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin')
        return render_template('login.html', error='Wrong password.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect('/')


# --- ROUTES: ADMIN ---

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin'):
        return redirect('/login')

    if request.method == 'POST':
        if 'start' in request.form:
            GAME_STATE['active'] = True
        if 'stop' in request.form:
            GAME_STATE['active'] = False

        if 'add_team' in request.form:
            db.session.add(Team(name=request.form['name'], ip=request.form['ip']))
            db.session.commit()

        if 'add_service' in request.form:
            db.session.add(Service(
                name=request.form['name'],
                checker_file=os.path.basename(request.form['checker_file']),
                flags_per_tick=int(request.form.get('flags_per_tick', 1))
            ))
            db.session.commit()

        if 'delete_team' in request.form:
            tid = int(request.form['delete_team'])
            Flag.query.filter_by(team_id=tid).delete()
            CheckerResult.query.filter_by(team_id=tid).delete()
            TeamServiceScore.query.filter_by(team_id=tid).delete()
            Team.query.filter_by(id=tid).delete()
            db.session.commit()

        if 'delete_service' in request.form:
            sid = int(request.form['delete_service'])
            Flag.query.filter_by(service_id=sid).delete()
            CheckerResult.query.filter_by(service_id=sid).delete()
            TeamServiceScore.query.filter_by(service_id=sid).delete()
            Service.query.filter_by(id=sid).delete()
            db.session.commit()

        if 'save_config' in request.form:
            set_config('tick_duration', int(request.form['tick_duration']))
            set_config('sla_bonus_k',   float(request.form['sla_bonus_k']))
            db.session.commit()
            do_reset()

        if 'reset' in request.form:
            do_reset()

        return redirect('/admin')

    checkers_avail = sorted(
        f for f in os.listdir('checkers')
        if os.path.isfile(os.path.join('checkers', f))
        and not f.startswith('.')
    ) if os.path.exists('checkers') else []

    # Logs da TSS — nessun scan di CheckerResult
    all_tss  = TeamServiceScore.query.all()
    all_last = {(r.team_id, r.service_id): {'status': r.last_status, 'tick': r.last_tick}
                for r in all_tss if r.last_status != 'UNKNOWN'}

    # Mappa id -> nome per team e service
    teams_list    = Team.query.all()
    services_list = Service.query.all()
    team_names    = {t.id: t.name    for t in teams_list}
    service_names = {s.id: s.name    for s in services_list}

    # Errori in memoria arricchiti con nomi leggibili
    with errors_lock:
        checker_errors = [
            {
                'team':    team_names.get(tid, f'Team {tid}'),
                'service': service_names.get(sid, f'Service {sid}'),
                'tick':    v['tick'],
                'error':   v['error'],
            }
            for (tid, sid), v in sorted(CHECKER_ERRORS.items(), key=lambda x: x[1]['tick'], reverse=True)
        ]

    cfg = {
        'tick_duration': get_tick_duration(),
        'sla_bonus_k':   get_sla_bonus_k(),
    }

    return render_template('admin.html',
                           teams=teams_list,
                           services=services_list,
                           state=GAME_STATE,
                           checkers=checkers_avail,
                           logs=all_last,
                           checker_errors=checker_errors,
                           cfg=cfg)


# --- ROUTES: API ---

@app.route('/api/flagids/<int:service_id>')
def get_flagids(service_id):
    min_tick = max(0, GAME_STATE['tick'] - 5)
    flags = Flag.query.filter(
        Flag.service_id == service_id,
        Flag.tick_created >= min_tick,
        Flag.captured == False
    ).all()

    # Pre-carica i team in un dict — evita N+1
    team_ids = {f.team_id for f in flags}
    teams    = {t.id: t for t in Team.query.filter(Team.id.in_(team_ids)).all()}

    result = {}
    for f in flags:
        team = teams.get(f.team_id)
        if team:
            result.setdefault(team.ip, []).append(f.flag_id)
    return jsonify(result)

@app.route('/api/submit', methods=['POST'])
def submit_flag():
    api_key = request.headers.get('X-Team-Key')
    team = Team.query.filter_by(api_key=api_key).first()
    if not team:
        return jsonify({'error': 'Invalid API Key'}), 401

    now = time.time()
    with state_lock:
        if now - RATE_LIMITS.get(team.id, 0) < 1.0:
            return jsonify({'error': 'Rate limit (1 req/sec)'}), 429
        RATE_LIMITS[team.id] = now

    body = request.get_json(force=True, silent=True) or {}

    # Accetta {"flag": "..."} oppure {"flags": [...]} — type-safe
    if 'flags' in body:
        raw = body['flags']
        if not isinstance(raw, list):
            return jsonify({'error': '"flags" must be a list'}), 400
        flag_strings = [f for f in raw if isinstance(f, str)][:MAX_FLAGS_PER_SUBMIT]
    elif 'flag' in body:
        if not isinstance(body['flag'], str):
            return jsonify({'error': '"flag" must be a string'}), 400
        flag_strings = [body['flag']]
    else:
        return jsonify({'error': 'Missing flag or flags field'}), 400

    results = []
    for flag_str in flag_strings:
        try:
            flag = Flag.query.filter_by(flag_string=flag_str).with_for_update().first()
            if not flag:
                results.append({'flag': flag_str, 'status': 'INVALID', 'points': 0.0})
                continue
            if flag.team_id == team.id:
                results.append({'flag': flag_str, 'status': 'OWN_FLAG', 'points': 0.0})
                continue
            if GAME_STATE['tick'] - flag.tick_created > 5:
                results.append({'flag': flag_str, 'status': 'EXPIRED', 'points': 0.0})
                continue
            if flag.captured:
                results.append({'flag': flag_str, 'status': 'ALREADY_CAPTURED', 'points': 0.0})
                continue

            BASE = 10.0
            attacker_tss = get_or_create_tss(team.id, flag.service_id)
            victim_tss   = get_or_create_tss(flag.team_id, flag.service_id)

            attacker_sla  = get_sla_from_tss(attacker_tss)
            victim_sla    = get_sla_from_tss(victim_tss)
            points_gained = round(BASE * attacker_sla, 2)
            points_lost   = round((BASE / 2) * victim_sla, 2)

            db.session.execute(
                update(Team).where(Team.id == team.id)
                .values(score=Team.score + points_gained)
            )
            db.session.execute(
                update(Team).where(Team.id == flag.team_id)
                .values(score=Team.score - points_lost)
            )
            db.session.execute(
                update(TeamServiceScore)
                .where(TeamServiceScore.team_id == team.id,
                       TeamServiceScore.service_id == flag.service_id)
                .values(flags_gained=TeamServiceScore.flags_gained + 1)
            )
            db.session.execute(
                update(TeamServiceScore)
                .where(TeamServiceScore.team_id == flag.team_id,
                       TeamServiceScore.service_id == flag.service_id)
                .values(flags_lost=TeamServiceScore.flags_lost + 1)
            )
            flag.captured = True
            db.session.commit()  # commit per-flag: un crash non butta via l'intero batch
            results.append({'flag': flag_str, 'status': 'ACCEPTED', 'points': points_gained})

        except Exception as e:
            db.session.rollback()
            results.append({'flag': flag_str, 'status': 'ERROR', 'points': 0.0})
            print(f'Submit error for {flag_str}: {e}')

    return jsonify(results)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Config.query.get('tick_duration'):
            set_config('tick_duration', os.environ.get('TICK_DURATION', 60))
        if not Config.query.get('sla_bonus_k'):
            set_config('sla_bonus_k', os.environ.get('SLA_BONUS_K', 5.0))
        db.session.commit()
    threading.Thread(target=tick_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, threaded=True)