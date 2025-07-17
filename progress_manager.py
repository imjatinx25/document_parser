from collections import defaultdict
import asyncio
import json

class progress_manager:
    def __init__(self):
        self.listeners = {}
        self.progress_data = {}

    def init_task(self, task_id: str):
        self.progress_data[task_id] = {
            "progress": 0,
            "message": "Task initialized.",
            "data": None
        }
        self.listeners[task_id] = asyncio.Queue()

    async def update_progress(self, task_id: str, progress: int, message: str, data: dict = None):
        if task_id not in self.progress_data:
            self.init_task(task_id)

        # Persist progress data
        self.progress_data[task_id] = {
            "progress": progress,
            "message": message,
            "data": data
        }

        payload = {
            "progress": progress,
            "message": message,
            "data": data
        }

        if task_id in self.listeners:
            await self.listeners[task_id].put(payload)

    async def listen(self, task_id: str):
        if task_id not in self.listeners:
            yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
            return

        while True:
            data = await self.listeners[task_id].get()
            yield f"data: {json.dumps(data)}\n\n"
            if data["progress"] >= 100:
                break

    def get_progress(self, task_id: str):
        return self.progress_data.get(task_id, None)

    def complete_task(self, task_id: str, final_data: dict = None):
        if task_id in self.progress_data:
            self.progress_data[task_id].update({
                "progress": 100,
                "message": "Processing complete!",
                "data": final_data
            })


progress_manager = progress_manager()