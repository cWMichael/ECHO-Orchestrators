from fastapi import HTTPException

class CustomHTTPException(HTTPException):
    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)

def raise_404(detail="Not Found"):
    raise CustomHTTPException(status_code=404, detail=detail)
