"""ComfyUI-WordPop — Premium word-by-word subtitle generator node."""

from .wordpop_node import WordPop

NODE_CLASS_MAPPINGS = {
    "WordPop": WordPop,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WordPop": "Word Pop Subtitles",
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
