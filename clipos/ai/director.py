"""Bounded local director context assembled from real persisted analysis.

No inference is claimed for missing analysis. Specialized vision/transcription
continue to run through the existing pipeline, not through the text model.
"""
from .editing_agent import propose_plan,InvalidEditPlan

def project_context(db,project_id):
    row=db.get_project(project_id)
    if row is None:raise InvalidEditPlan('Open an existing local project first')
    project=dict(row);transcript=db.get_transcript(project_id)
    clips=[]
    for row in db.list_clips(project_id)[:24]:
        clip=dict(row)
        clips.append({key:clip[key] for key in ('id','start_time','end_time','engagement_score','reason')})
    return {'source':{key:project[key] for key in ('duration','width','height','fps','has_audio')},
            'candidate_clips':clips,
            'transcription': 'available' if transcript else 'missing; run local analysis before transcript-based selection',
            'visual_analysis':'No verified detection artifact supplied to this plan; do not invent people/objects/crops'}, (transcript['full_text'][:12000] if transcript else '')

def propose_project_plan(db,project_id,instruction,current_settings):
    evidence,text=project_context(db,project_id)
    evidence['current_edit_settings']=current_settings
    return propose_plan(instruction,evidence['source']['duration'],text,evidence,
                        db.get_setting('ollama_host','http://127.0.0.1:11434'),
                        db.get_setting('llm_model','gemma:7b'),profile=db.get_setting('director_profile','Balanced'))
