class BaseTplusException(Exception):
    """
    Base exception class.
    """


class MissingClientUserError(BaseTplusException):
    """
    Raised when a user is not specified in a client when required.
    """

    def __init__(self, context: str | None = None):
        message = "User required. Create client with a default user or specify user in request."
        if context is not None:
            message = f"{message}. Context: {context}"

        super().__init__(message)
