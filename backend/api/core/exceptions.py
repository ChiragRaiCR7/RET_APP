from fastapi import HTTPException, status

class Unauthorized(HTTPException):
    def __init__(self, detail="Unauthorized"):
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail)

class Forbidden(HTTPException):
    def __init__(self, detail="Forbidden"):
        super().__init__(status.HTTP_403_FORBIDDEN, detail)

class NotFound(HTTPException):
    def __init__(self, detail="Not found"):
        super().__init__(status.HTTP_404_NOT_FOUND, detail)

class BadRequest(HTTPException):
    def __init__(self, detail="Bad request"):
        super().__init__(status.HTTP_400_BAD_REQUEST, detail)
