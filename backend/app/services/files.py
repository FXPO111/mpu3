def presign_upload(filename: str) -> dict:
    return {"filename": filename, "upload_url": f"https://storage.local/upload/{filename}"}