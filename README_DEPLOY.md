# Cloud Run endpoints

PROD (public):
https://fastapi-run-oobzrmikna-ew.a.run.app

DEV (private - needs token):
https://fastapi-run-dev-oobzrmikna-ew.a.run.app

## Health checks
PROD:
curl -i https://fastapi-run-oobzrmikna-ew.a.run.app/health

DEV (auth):
curl -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" https://fastapi-run-dev-oobzrmikna-ew.a.run.app/health

## Docs
PROD:
https://fastapi-run-oobzrmikna-ew.a.run.app/docs

DEV (auth):
curl -I -H "Authorization: Bearer $(gcloud auth print-identity-token)" https://fastapi-run-dev-oobzrmikna-ew.a.run.app/docs
