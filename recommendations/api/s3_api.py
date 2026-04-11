from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from recommendations.security import fetch_rate_limit, require_s3_api_key
from recommendations.services.s3_service import S3Service


router = APIRouter()
service = S3Service()


@router.post("/upload", dependencies=[Depends(require_s3_api_key)])
def upload_client_dataset_file(
	client: str = Query(..., min_length=2, max_length=50),
	dataset: str = Query(..., min_length=2, max_length=50),
	file: UploadFile = File(...),
):
	try:
		return service.upload_file(client=client, dataset=dataset, file=file)
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))


@router.get("/fetch", dependencies=[Depends(require_s3_api_key), Depends(fetch_rate_limit)])
def fetch_client_dataset_file(
	client: str = Query(..., min_length=2, max_length=50),
	dataset: str = Query(..., min_length=2, max_length=50),
	filename: str | None = Query(default=None),
):
	try:
		result = service.fetch_file(client=client, dataset=dataset, filename=filename)
		content_disposition = f'attachment; filename="{result["filename"]}"'

		return StreamingResponse(
			result["stream"],
			media_type=result["content_type"],
			headers={
				"Content-Disposition": content_disposition,
				"X-S3-Key": result["key"],
			},
		)
	except Exception as e:
		raise HTTPException(status_code=404, detail=str(e))


@router.get("/fetch_all", dependencies=[Depends(require_s3_api_key), Depends(fetch_rate_limit)])
def fetch_all_client_files(
	client: str = Query(..., min_length=2, max_length=50),
	dataset: str | None = Query(default=None, min_length=2, max_length=50),
	max_keys: int = Query(default=100, ge=1, le=500),
	continuation_token: str | None = Query(default=None),
	include_download_url: bool = Query(default=False),
):
	try:
		return service.list_files(
			client=client,
			dataset=dataset,
			max_keys=max_keys,
			continuation_token=continuation_token,
			include_download_url=include_download_url,
		)
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))


@router.post("/sync", dependencies=[Depends(require_s3_api_key)])
def sync_client_latest_data_to_processed(
	client: str = Query(..., min_length=2, max_length=50),
	datasets: str | None = Query(default=None, description="Comma-separated datasets (optional)"),
	overwrite: bool = Query(default=True),
):
	try:
		dataset_list = None
		if datasets:
			dataset_list = [item.strip() for item in datasets.split(",") if item.strip()]

		return service.sync_latest_to_processed(
			client=client,
			datasets=dataset_list,
			overwrite=overwrite,
		)
	except Exception as e:
		raise HTTPException(status_code=400, detail=str(e))
