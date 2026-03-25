from pydantic_settings import BaseSettings


class Settings(BaseSettings):
   

    host_url: str
    api_key: str   # ✅ FIXED

    

    @property
    def meili_url(self):   # ✅ rename (more accurate)
        return self.host_url

    class Config:
        env_file = ".env"
        case_sensitive = False   # ✅ IMPORTANT


settings = Settings()