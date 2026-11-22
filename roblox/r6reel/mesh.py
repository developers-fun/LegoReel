"""Shared mesh container. Every module that makes geometry returns a Mesh."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass
class Mesh:
    """Indexed triangle mesh. Y-up, right-handed, units = Roblox studs.

    positions (N,3) float32, normals (N,3) float32 (unit), uvs (N,2) float32,
    indices (M,3) uint32, counter-clockwise winding when seen from outside.
    """
    positions: np.ndarray
    normals: np.ndarray
    uvs: np.ndarray
    indices: np.ndarray

    def __post_init__(self):
        self.positions = np.ascontiguousarray(self.positions, np.float32).reshape(-1, 3)
        self.normals = np.ascontiguousarray(self.normals, np.float32).reshape(-1, 3)
        self.uvs = np.ascontiguousarray(self.uvs, np.float32).reshape(-1, 2)
        self.indices = np.ascontiguousarray(self.indices, np.uint32).reshape(-1, 3)
        n = len(self.positions)
        assert len(self.normals) == n and len(self.uvs) == n, "attribute length mismatch"
        assert self.indices.size == 0 or self.indices.max() < n, "index out of range"

    def transformed(self, m4: np.ndarray) -> "Mesh":
        """Return a copy transformed by a 4x4 matrix (column-vector convention)."""
        m4 = np.asarray(m4, np.float64)
        p = np.c_[self.positions, np.ones(len(self.positions))] @ m4.T
        nm = np.linalg.inv(m4[:3, :3]).T
        n = self.normals @ nm.T
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        return Mesh(p[:, :3], n, self.uvs.copy(), self.indices.copy())

    @staticmethod
    def merge(meshes: list["Mesh"]) -> "Mesh":
        off, idx = 0, []
        for m in meshes:
            idx.append(m.indices + off); off += len(m.positions)
        return Mesh(np.concatenate([m.positions for m in meshes]),
                    np.concatenate([m.normals for m in meshes]),
                    np.concatenate([m.uvs for m in meshes]),
                    np.concatenate(idx))
