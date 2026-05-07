import inspect


def test_lifespan_cancels_background_tasks_on_shutdown():
    import main

    source = inspect.getsource(main._cancel_background_tasks)
    lifespan_source = inspect.getsource(main.lifespan)
    assert "app.state.background_tasks" in lifespan_source
    assert "task.cancel()" in source
    assert "asyncio.gather(*tasks, return_exceptions=True)" in source
    assert "await _cancel_background_tasks(background_tasks)" in lifespan_source


def test_lifespan_uses_structured_logging_not_prints():
    import main

    source = inspect.getsource(main.lifespan)
    assert "print(" not in source
    assert "log.info" in source
    assert "log.warning" in source


def test_background_tasks_log_unhandled_failures():
    import main

    source = inspect.getsource(main._create_background_tasks)
    callback_source = inspect.getsource(main._log_background_task_result)
    assert "add_done_callback(_log_background_task_result)" in source
    assert "log.exception" in callback_source
