"""Opt-in, bounded local ranking preferences from distinct successful exports.

Uses only stored measured features and existing export records. No telemetry,
LLM-generated feedback or presumed audience retention. Reset deletes snapshots.
"""
import json
import math

CHANNELS=('motion','loudness_jump','energy','story','hook')


def features(values):
    return {key:float(value) for key,value in values.items() if key in CHANNELS and
            type(value) in (int,float) and math.isfinite(value) and 0<=value<=1}


def learn(db):
    rows=db.query('''SELECT c.id,c.settings,EXISTS(SELECT 1 FROM exports e
        WHERE e.clip_id=c.id AND e.status='done' AND e.size_bytes>0) AS kept
        FROM clips c ORDER BY c.id DESC LIMIT 5000''')
    library=[];kept=[]
    for row in rows:
        try:profile=features(json.loads(row['settings']).get('selection_features',{}))
        except (ValueError,TypeError,AttributeError):continue
        if profile:
            library.append(profile)
            if row['kept']:kept.append(profile)
    if len(kept)<8:return {'status':'insufficient_exports','samples':len(kept),'bias':{}}
    bias={}
    for key in CHANNELS:
        all_values=[r[key] for r in library if key in r];positive=[r[key] for r in kept if key in r]
        if len(positive)>=8 and all_values:
            difference=sum(positive)/len(positive)-sum(all_values)/len(all_values)
            bias[key]=max(-.15,min(.15,difference*.5))
    return {'status':'active','samples':len(kept),'baseline':len(library),'bias':bias}


def adjustment(scores,profile):
    clean=features(scores);bias=profile.get('bias',{})
    # At most +/- 4 ranking points, never modify the measured candidate score.
    return max(-4.,min(4.,sum((clean[k]-.5)*bias[k]*10 for k in clean if k in bias)))


def reset(db):
    with db._write_lock:
        with db.conn:
            last=0
            while True:
                rows=db.conn.execute('SELECT id,settings FROM clips WHERE id>? ORDER BY id LIMIT 200',(last,)).fetchall()
                if not rows:break
                for row in rows:
                    last=row['id']
                    try:data=json.loads(row['settings'])
                    except (ValueError,TypeError):continue
                    if isinstance(data,dict) and 'selection_features' in data:
                        del data['selection_features']
                        db.conn.execute('UPDATE clips SET settings=? WHERE id=?',(json.dumps(data),row['id']))
