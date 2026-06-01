"""How spotter composes with the real fleet-python SDK.

Fleet's flow is: load a Task, make an environment, let your agent act, then call
`task.verify_detailed_async(...)` to get a completion score. spotter wraps that
last step: it takes Fleet's result dict plus the agent's action trace and returns
a safety-gated result in the same shape.

A live run needs a FLEET_API_KEY (a Fleet account), so the __main__ block runs an
OFFLINE mock that uses the bundled scenario. The live function shows the exact
integration shape you would deploy for a customer.
"""
import os
import json
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spotter import Spotter, DEFAULT_CHECKS, TaskContext


async def gate_live(task_key: str, collect_actions, allowlist, final_state):
    """Illustrative live integration. `collect_actions` is your instrumentation
    that records what the agent did inside the env as a list[Action]."""
    import fleet  # pip install fleet-python

    tasks = await fleet.load_tasks_async(keys=[task_key])
    task = tasks[0]
    env = await fleet.env.make_async(
        env_key=task.env_key,
        data_key=task.data_key,
        env_variables=task.env_variables,
        ttl_seconds=7200,
        run_id=f"spotter-{task_key}",
    )
    try:
        # ... your agent does the task against env.urls.app[0] ...
        actions = collect_actions(env)                       # your trace
        fleet_result = await task.verify_detailed_async(env.instance_id)
        ctx = TaskContext(
            key=task.key, prompt=task.prompt, env_key=task.env_key,
            actions=actions, allowlist=allowlist, final_state=final_state,
        )
        return Spotter(DEFAULT_CHECKS).gate_fleet_result(ctx, fleet_result)
    finally:
        await env.close()


def gate_mock():
    """Offline: reuse the bundled CRM scenario and a stand-in Fleet result."""
    from spotter.scenarios import crm_closure, crm_closure_completion

    fleet_result = {
        "key": crm_closure.key, "version": 4, "success": True,
        "result": crm_closure_completion, "error": None,
        "execution_time_ms": 2291, "stdout": "",
    }
    gated = Spotter(DEFAULT_CHECKS).gate_fleet_result(crm_closure, fleet_result)
    return gated


if __name__ == "__main__":
    print(json.dumps(gate_mock(), indent=2))
