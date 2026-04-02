from pydantic import BaseModel


class Tenant(BaseModel):
    id: str
    name: str