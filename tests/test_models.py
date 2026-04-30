from app.models import GRAPH_TEMPLATE


def test_graph_template_accepts_device():
    result = GRAPH_TEMPLATE.format(model_path="/some/path", device="CPU")
    assert 'device: "CPU"' in result


def test_graph_template_gpu_default_usable():
    result = GRAPH_TEMPLATE.format(model_path="/models/qwen", device="GPU")
    assert 'device: "GPU"' in result
    assert 'models_path: "/models/qwen"' in result


def test_graph_template_npu():
    result = GRAPH_TEMPLATE.format(model_path="/m", device="NPU")
    assert 'device: "NPU"' in result
