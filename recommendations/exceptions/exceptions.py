class AppException(Exception):
    """Base exception for all custom errors"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


class NotFoundException(AppException):
    def __init__(self, message="Resource not found"):
        super().__init__(message, status_code=404)


class BadRequestException(AppException):
    def __init__(self, message="Bad request"):
        super().__init__(message, status_code=400)


class meiliException(AppException):
    def __init__(self, message="meili operation failed"):
        super().__init__(message, status_code=409)


class PipelineException(AppException):
    def __init__(self, message="Trending pipeline failed"):
        super().__init__(message, status_code=409)