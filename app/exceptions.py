class NotFoundError(Exception):
    def __init__(self, name: str, namespace: str):
        super().__init__(f'Job "{name}" not found in namespace "{namespace}".')
        self.name      = name
        self.namespace = namespace