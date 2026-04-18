from os import environ

# Hide oTree's devserver debug footer ("Debug info / Restart as new participant /
# Basic info ..."). Participants should never see it.
environ.setdefault('OTREE_PRODUCTION', '1')
environ.setdefault('OTREE_ADMIN_PASSWORD', 'AdminDebate')

NUM_ROOMS = 82

ROOMS = [
    dict(
        name=f'debate_room_{i}',
        display_name=f'Debate Room {i}',
    )
    for i in range(1, NUM_ROOMS + 1)
]

SESSION_CONFIGS = [
    dict(
        name='debate',
        display_name='Debate (3-person chat, 5 min)',
        app_sequence=['debate'],
        num_demo_participants=3,
    ),
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
