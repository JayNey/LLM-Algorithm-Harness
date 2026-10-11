"""File service dependency shared by resource routes."""

from typing import cast

from fastapi import Request

from api.files.service import FileService


def file_service(request: Request) -> FileService:
    return cast(FileService, request.app.state.files)
