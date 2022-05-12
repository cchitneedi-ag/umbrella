from codecov.commands.base import BaseCommand

from .interactors.fetch_repository import FetchRepositoryInteractor
from .interactors.get_upload_token import GetUploadTokenInteractor
from .interactors.get_profiling_token import GetProfilingTokenInteractor
from .interactors.regenerate_profiling_token import RegenerateProfilingTokenInteractor


class RepositoryCommands(BaseCommand):
    def fetch_repository(self, owner, name):
        return self.get_interactor(FetchRepositoryInteractor).execute(owner, name)

    def get_upload_token(self, repository):
        return self.get_interactor(GetUploadTokenInteractor).execute(repository)
    
    def get_profiling_token(self, repository):
        return self.get_interactor(GetProfilingTokenInteractor).execute(repository)

    def regenerate_profiling_token(self,repoName):
        return self.get_interactor(RegenerateProfilingTokenInteractor).execute(repoName)

