from flask import (
    Blueprint,
    make_response,
    request,
)

from cah.routes.helpers import get_app_bot

bp_slash = Blueprint('slash', __name__)


@bp_slash.route('/api/slash', methods=['GET', 'POST'])
def handle_slash():
    """Handles a slash command"""
    event_data = request.form
    # Handle the command
    get_app_bot().process_slash_command(event_data)

    # Send HTTP 200 response with an empty body so Slack knows we're done
    return make_response('', 200)
