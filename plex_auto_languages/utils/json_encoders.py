import json
from datetime import datetime, date, time


class DateTimeEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for handling datetime objects.

    This encoder extends the standard JSON encoder to properly serialize
    datetime, date, and time objects by converting them to ISO 8601 format strings.

    Attributes:
        None
    """

    def default(self, o):
        """
        Override the default method to handle datetime-related objects.

        Converts datetime, date, and time objects to their ISO 8601 string
        representation. For other object types, delegates to the parent class.

        Args:
            o: The object to be serialized to JSON

        Returns:
            str: ISO 8601 formatted string for datetime objects
            Any: Result of the parent encoder's default method for other objects

        Raises:
            TypeError: When the object is not JSON serializable (raised by parent class)
        """
        if isinstance(o, (datetime, date, time)):
            return o.isoformat()
        return super().default(o)
