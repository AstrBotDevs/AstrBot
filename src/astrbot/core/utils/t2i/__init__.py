from abc import ABC, abstractmethod


class RenderStrategy(ABC):
    @abstractmethod
    def render(self, text: str, return_url: bool) -> str:
        pass

    @abstractmethod
    def render_custom_template(
        self, tmpl_str: str, tmpl_data: dict, return_url: bool
    ) -> str:
        pass
