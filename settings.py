from os import environ

# Hide oTree's devserver debug footer ("Debug info / Restart as new participant /
# Basic info ..."). Participants should never see it.
environ.setdefault('OTREE_PRODUCTION', '1')
environ.setdefault('OTREE_ADMIN_PASSWORD', 'AdminDebate')

NUM_ROOMS = 82

# Consultancy topics — slug (URL) + admin display name. Slugs are derived
# from the `general_topic` column of dataset_consultancy.csv; each slug has
# 10 prompt variants in that CSV (100 total). Room name convention mirrors
# the debate app: `<app>_room_<identifier>`.
CONSULT_TOPICS = [
    ('3d_bioprinting', '3D Bioprinting'),
    ('confirmation_of_the_existence_of_exoplanets', 'Confirmation of the Existence of Exoplanets'),
    ('controlled_nuclear_fusion', 'Controlled Nuclear Fusion'),
    ('exascale_computing', 'Exascale Computing'),
    ('imaging_black_holes', 'Imaging Black Holes'),
    ('lab_grown_embryo_models', 'Lab-grown Embryo Models'),
    ('mirror_life', 'Mirror Life'),
    ('operational_quantum_computers', 'Operational Quantum Computers'),
    ('spacecraft_capable_of_taking_civilians_to_space', 'Spacecraft Capable of Taking Civilians to Space'),
    ('supersonic_aircrafts', 'Supersonic Aircrafts'),
]

ROOMS = [
    dict(
        name=f'debate_room_{i}',
        display_name=f'Debate Room {i}',
    )
    for i in range(1, NUM_ROOMS + 1)
] + [
    dict(
        name=f'consult_room_{slug}',
        display_name=f'Consultancy: {name}',
    )
    for slug, name in CONSULT_TOPICS
]

SESSION_CONFIGS = [
    dict(
        name='debate',
        display_name='Debate (3-person chat, 5 min)',
        app_sequence=['debate'],
        num_demo_participants=3,
    ),
] + [
    # One session config per topic. `topic_slug` is read by consult/__init__.py
    # to look up the right prompt list. Bind admin-created sessions to the
    # matching `consult_room_<slug>` room (name parity keeps this obvious).
    dict(
        name=f'consult_{slug}',
        display_name=f'Consultancy: {name}',
        app_sequence=['consult'],
        num_demo_participants=10,
        topic_slug=slug,
    )
    for slug, name in CONSULT_TOPICS
]

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.00, participation_fee=0.00, doc=""
)

# participant.label is populated automatically from ?participant_label=<id>.
PARTICIPANT_FIELDS = []
SESSION_FIELDS = []

LANGUAGE_CODE = 'en'
REAL_WORLD_CURRENCY_CODE = 'USD'
USE_POINTS = False

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

DEMO_PAGE_INTRO_HTML = """
Debate study: participants enter via a room URL with
<code>?participant_label=&lt;id&gt;</code> and are grouped 3-per-room.
"""

SECRET_KEY = '3170613763936'

# Multi-web-dyno support: when REDIS_URL is set (Heroku Key-Value Store add-on),
# route Django Channels through Redis so >1 web dyno can share websocket state.
# Local devserver and single-dyno prod fall through to oTree's default layer.
_REDIS_URL = environ.get('REDIS_URL')
if _REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [_REDIS_URL]},
        },
    }
