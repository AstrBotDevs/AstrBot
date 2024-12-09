from ..star import star_registry, StarMetadata, star_map

def register_star(name: str, author: str, desc: str, version: str, repo: str = None):
    def decorator(cls):
        star_metadata = StarMetadata(
            name=name,
            author=author,
            desc=desc,
            version=version,
            repo=repo,
            star_cls_type=cls,
            module_path=cls.__module__
        )
        star_registry.append(star_metadata)
        star_map[cls.__module__] = star_metadata
        return cls
    
    return decorator
