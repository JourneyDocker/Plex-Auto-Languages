# This prevents the "<user> used a new device to access <server>" notifications from Plex.

import os
import uuid

os.environ["PLEXAPI_HEADER_IDENTIFIER"] = uuid.uuid3(
    uuid.NAMESPACE_DNS, "PlexAutoLanguages"
).hex
os.environ["PLEXAPI_HEADER_DEVICE_NAME"] = "PlexAutoLanguages"
os.environ["PLEXAPI_HEADER_PROVIDES"] = ""