"""
Exports a tiny 8→2 classifier as ONNX into the Triton model repo.
Requires: torch, onnx (installed in the API image).
"""
from pathlib import Path
import torch
import torch.nn as nn

class TinyNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.lin = nn.Linear(8, 2)
        self.softmax = nn.Softmax(dim=-1)
    def forward(self, x):
        return self.softmax(self.lin(x))

ROOT = Path(__file__).resolve().parents[1] / "services/inference/model_repository/trade_eligibility"
version = ROOT / "1"
version.mkdir(parents=True, exist_ok=True)

model = TinyNet().eval()
dummy = torch.randn(1, 8)
onnx_path = version / "model.onnx"

# export to ONNX with named I/O
torch.onnx.export(
    model,
    dummy,
    onnx_path.as_posix(),
    input_names=["input"],
    output_names=["prob"],
    opset_version=13,
    dynamic_axes={"input": {0: "batch"}, "prob": {0: "batch"}},
)

print(f"Wrote {onnx_path}")
