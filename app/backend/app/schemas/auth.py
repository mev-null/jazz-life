from pydantic import BaseModel, ConfigDict


class AuthUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spotify_id: str
    display_name: str
    image_url: str | None
