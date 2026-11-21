from trading_system.domain import ExecutionResult, OrderRequest, Side
from trading_system.execution.base import ExecutionAdapter
from trading_system.execution.paper import PaperExecutor


def test_paper_executor_implements_execution_adapter_contract():
    executor = PaperExecutor()
    order = OrderRequest("BTC/USDT", Side.BUY, 0.01, 60_000)

    assert isinstance(executor, ExecutionAdapter)
    result = executor.execute(order)
    assert isinstance(result, ExecutionResult)
    assert result.simulated is True
