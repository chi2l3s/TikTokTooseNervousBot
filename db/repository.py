from sqlalchemy import select
from db.models import UserSettings
from db.session import async_session

class SettingsRepository:
    @staticmethod
    async def get_settings(user_id: int) -> UserSettings:
        async with async_session() as session:
            stmt = select(UserSettings).where(UserSettings.user_id == user_id)
            result = await session.execute(stmt)
            settings = result.scalar_one_or_none()
            
            if not settings:
                settings = UserSettings(user_id=user_id)
                session.add(settings)
                await session.commit()
                await session.refresh(settings)
                
            return settings
        
    @staticmethod
    async def update_settings(user_id: int, **kwargs) -> UserSettings:
        async with async_session() as session:
            stmt = select(UserSettings).where(UserSettings.user_id == user_id)
            result = await session.execute(stmt)
            settings = result.scalar_one_or_none()
            
            if not settings:
                settings = UserSettings(user_id=user_id, **kwargs)
                session.add(settings)
            else:
                for key, value in kwargs.items():
                    if hasattr(settings, key):
                        setattr(settings, key, value)
                        
            await session.commit()
            await session.refresh(settings)
            return settings