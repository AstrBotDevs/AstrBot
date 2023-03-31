from model.command.command import Command
from model.provider.provider_rev_edgegpt import ProviderRevEdgeGPT

class CommandRevEdgeGPT(Command):
    def __init__(self, provider: ProviderRevEdgeGPT):
        super().__init__(provider)
        
    def check_command(self, message: str):
        hit, res = super().check_command(message)
        if hit:
            return res
        
        return False, None
        
