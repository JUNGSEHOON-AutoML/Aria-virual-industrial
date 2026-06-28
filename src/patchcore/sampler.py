import abc
from typing import Union, Tuple, Optional
import logging

import numpy as np
import torch
import torch.nn.functional as F
import tqdm

# sklearn is optional — only required for PCA whitening
try:
    from sklearn.decomposition import PCA as SklearnPCA
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

LOGGER = logging.getLogger(__name__)


def compute_memory_bank_stats(features, class_name, phase, **kwargs):
    """
    Compute and log memory bank statistics.
    
    Phase 2.17 (Package D): Debugging statistics for memory bank quality.
    
    Args:
        features: Selected feature patches [N, D] (torch.Tensor)
        class_name: Class name
        phase: Experiment phase
        **kwargs: Additional metadata (backbone, k_config, etc.)
    """
    try:
        from patchcore.logging_utils import append_memory_stats
    except ImportError:
        LOGGER.warning("logging_utils not available, skipping memory stats")
        return
    
    N = len(features)
    
    if N < 2:
        LOGGER.warning(f"Memory bank too small ({N} patches), skipping stats")
        return
    
    # Normalize for cosine distance
    features_norm = F.normalize(features, p=2, dim=1)
    
    # Compute pairwise cosine distances (sample if too large)
    if N > 5000:
        # Sample 5000 patches for efficiency
        sample_indices = torch.randperm(N, device=features.device)[:5000]
        features_sample = features_norm[sample_indices]
    else:
        features_sample = features_norm
    
    # Compute pairwise cosine similarity
    cos_sim = torch.mm(features_sample, features_sample.T)
    cos_dist = 1.0 - cos_sim
    
    # Get upper triangle (exclude diagonal)
    mask = torch.triu(torch.ones_like(cos_dist), diagonal=1).bool()
    distances = cos_dist[mask].cpu().numpy()
    
    if len(distances) == 0:
        LOGGER.warning(f"No pairwise distances computed for {class_name}")
        return
    
    min_dist = float(np.min(distances))
    median_dist = float(np.median(distances))
    max_dist = float(np.max(distances))
    
    # Log statistics
    LOGGER.info(
        f"Memory bank stats [{class_name}]: size={N}, "
        f"dist=[min={min_dist:.4f}, median={median_dist:.4f}, max={max_dist:.4f}]"
    )
    
    # Save to CSV
    append_memory_stats(
        phase=phase,
        class_name=class_name,
        backbone=kwargs.get('backbone', 'wideresnet50'),
        k_config=kwargs.get('k_config', '1'),
        d2_mode=kwargs.get('d2_mode', 'none'),
        p=kwargs.get('p', 0.10),
        tau=kwargs.get('tau', 0.01),
        bank_size=N,
        min_dist=min_dist,
        median_dist=median_dist,
        max_dist=max_dist,
        random_fallbacks=kwargs.get('random_fallbacks', 0),
        rejected_by_tau=kwargs.get('rejected_by_tau', 0)
    )


class IdentitySampler:
    """
    Sampler that returns the input features as is.
    """
    def __init__(self, percentage: float, device: torch.device):
        self.percentage = percentage
        self.device = device
    
    def run(
        self, features: Union[torch.Tensor, np.ndarray]
    ) -> Union[torch.Tensor, np.ndarray]:
        return features


class BaseSampler(abc.ABC):
    def __init__(self, percentage: float):
        if not 0 < percentage < 1:
            raise ValueError("Percentage value not in (0, 1).")
        self.percentage = percentage

    @abc.abstractmethod
    def run(
        self, features: Union[torch.Tensor, np.ndarray]
    ) -> Union[torch.Tensor, np.ndarray]:
        pass

    def _store_type(self, features: Union[torch.Tensor, np.ndarray]) -> None:
        self.features_is_numpy = isinstance(features, np.ndarray)
        if not self.features_is_numpy:
            self.features_device = features.device

    def _restore_type(self, features: torch.Tensor) -> Union[torch.Tensor, np.ndarray]:
        if self.features_is_numpy:
            return features.cpu().numpy()
        return features.to(self.features_device)


class GreedyCoresetSampler(BaseSampler):
    def __init__(
        self,
        percentage: float,
        device: torch.device,
        dimension_to_project_features_to=128,
    ):
        """Greedy Coreset sampling base class."""
        super().__init__(percentage)

        self.device = device
        self.dimension_to_project_features_to = dimension_to_project_features_to

    def _reduce_features(self, features):
        if features.shape[1] == self.dimension_to_project_features_to:
            return features
        mapper = torch.nn.Linear(
            features.shape[1], self.dimension_to_project_features_to, bias=False
        )
        _ = mapper.to(self.device)
        features = features.to(self.device)
        return mapper(features)

    def run(
        self, features: Union[torch.Tensor, np.ndarray]
    ) -> Union[torch.Tensor, np.ndarray]:
        """Subsamples features using Greedy Coreset.

        Args:
            features: [N x D]
        """
        if self.percentage == 1:
            return features
        self._store_type(features)
        if isinstance(features, np.ndarray):
            features = torch.from_numpy(features)
        reduced_features = self._reduce_features(features)
        sample_indices = self._compute_greedy_coreset_indices(reduced_features)
        features = features[sample_indices]
        return self._restore_type(features)

    @staticmethod
    def _compute_batchwise_differences(
        matrix_a: torch.Tensor, matrix_b: torch.Tensor
    ) -> torch.Tensor:
        """Computes batchwise Euclidean distances using PyTorch."""
        a_times_a = matrix_a.unsqueeze(1).bmm(matrix_a.unsqueeze(2)).reshape(-1, 1)
        b_times_b = matrix_b.unsqueeze(1).bmm(matrix_b.unsqueeze(2)).reshape(1, -1)
        a_times_b = matrix_a.mm(matrix_b.T)

        return (-2 * a_times_b + a_times_a + b_times_b).clamp(0, None).sqrt()

    def _compute_greedy_coreset_indices(self, features: torch.Tensor) -> np.ndarray:
        """Runs iterative greedy coreset selection.

        Args:
            features: [NxD] input feature bank to sample.
        """
        distance_matrix = self._compute_batchwise_differences(features, features)
        coreset_anchor_distances = torch.norm(distance_matrix, dim=1)

        coreset_indices = []
        num_coreset_samples = int(len(features) * self.percentage)

        for _ in range(num_coreset_samples):
            select_idx = torch.argmax(coreset_anchor_distances).item()
            coreset_indices.append(select_idx)

            coreset_select_distance = distance_matrix[
                :, select_idx : select_idx + 1  # noqa E203
            ]
            coreset_anchor_distances = torch.cat(
                [coreset_anchor_distances.unsqueeze(-1), coreset_select_distance], dim=1
            )
            coreset_anchor_distances = torch.min(coreset_anchor_distances, dim=1).values

        return np.array(coreset_indices)


class ApproximateGreedyCoresetSampler(GreedyCoresetSampler):
    def __init__(
        self,
        percentage: float,
        device: torch.device,
        number_of_starting_points: int = 10,
        dimension_to_project_features_to: int = 128,
    ):
        """Approximate Greedy Coreset sampling base class."""
        self.number_of_starting_points = number_of_starting_points
        super().__init__(percentage, device, dimension_to_project_features_to)

    def _compute_greedy_coreset_indices(self, features: torch.Tensor) -> np.ndarray:
        """Runs approximate iterative greedy coreset selection.

        This greedy coreset implementation does not require computation of the
        full N x N distance matrix and thus requires a lot less memory, however
        at the cost of increased sampling times.

        Args:
            features: [NxD] input feature bank to sample.
        """
        number_of_starting_points = np.clip(
            self.number_of_starting_points, None, len(features)
        )
        start_points = np.random.choice(
            len(features), number_of_starting_points, replace=False
        ).tolist()

        approximate_distance_matrix = self._compute_batchwise_differences(
            features, features[start_points]
        )
        approximate_coreset_anchor_distances = torch.mean(
            approximate_distance_matrix, axis=-1
        ).reshape(-1, 1)
        coreset_indices = []
        num_coreset_samples = int(len(features) * self.percentage)

        with torch.no_grad():
            for _ in tqdm.tqdm(range(num_coreset_samples), desc="Subsampling..."):
                select_idx = torch.argmax(approximate_coreset_anchor_distances).item()
                coreset_indices.append(select_idx)
                coreset_select_distance = self._compute_batchwise_differences(
                    features, features[select_idx : select_idx + 1]  # noqa: E203
                )
                approximate_coreset_anchor_distances = torch.cat(
                    [approximate_coreset_anchor_distances, coreset_select_distance],
                    dim=-1,
                )
                approximate_coreset_anchor_distances = torch.min(
                    approximate_coreset_anchor_distances, dim=1
                ).values.reshape(-1, 1)

        return np.array(coreset_indices)


class ProbabilisticCoresetSampler(GreedyCoresetSampler):
    """
    Probabilistic D² Coreset Sampler (k-means++ style) with Cosine Distance.
    
    Phase 2.15: Modified to use cosine distance instead of L2 distance
    for consistency with τ-filtering (Stage 2).
    
    Phase 2.26: Added density-aware sampling for better diversity control.
    
    Instead of deterministic farthest-first (argmax), this sampler uses
    probabilistic selection where P(point) ∝ D²(point, nearest_selected).
    
    This is more robust to outliers and noise, making it suitable for
    fine-grained object classes (screw, bottle, hazelnut, cable, capsule).
    """
    
    def __init__(
        self,
        percentage: float,
        device: torch.device,
        number_of_starting_points: int = 10,
        dimension_to_project_features_to: int = 128,
        d2_exponent: float = 2.0,
        density_weight: float = 0.0,
    ):
        """
        Probabilistic D² Coreset sampling.
        
        Phase 2.15b: Added d2_exponent for adaptive diversity control.
        Phase 2.26: Added density_weight for density-aware sampling.
        
        Args:
            percentage: Sampling percentage
            device: Torch device
            number_of_starting_points: Number of anchor points for approximation
            dimension_to_project_features_to: PCA dimension
            d2_exponent: Exponent for distance-based probability (default: 2.0)
                - 1.0: Linear (soft, outlier-robust)
                - 2.0: Standard D² (k-means++)
                - 2.5: Aggressive (high diversity)
            density_weight: Weight for density-aware sampling (default: 0.0)
                - 0.0: Pure distance-based (original D²)
                - 0.3-0.5: Moderate density awareness (texture classes)
                - 0.1-0.2: Light density awareness (structural classes)
        """
        self.number_of_starting_points = number_of_starting_points
        self.d2_exponent = d2_exponent
        self.density_weight = density_weight
        super().__init__(percentage, device, dimension_to_project_features_to)
    
    @staticmethod
    def _compute_cosine_distances(
        matrix_a: torch.Tensor, matrix_b: torch.Tensor
    ) -> torch.Tensor:
        """
        Computes batchwise cosine distances.
        
        Phase 2.15: Cosine distance for metric consistency with τ-filtering.
        
        Args:
            matrix_a: [N x D] feature matrix
            matrix_b: [M x D] feature matrix
            
        Returns:
            [N x M] cosine distance matrix (1 - cosine_similarity)
        """
        # Normalize features
        matrix_a_norm = F.normalize(matrix_a, p=2, dim=1)
        matrix_b_norm = F.normalize(matrix_b, p=2, dim=1)
        
        # Cosine similarity
        cos_sim = torch.mm(matrix_a_norm, matrix_b_norm.T)
        
        # Cosine distance: 1 - cos_sim
        return 1.0 - cos_sim
    
    def _compute_local_density(self, features: torch.Tensor, k: int = 5) -> torch.Tensor:
        """
        Compute local density for each feature point.
        
        Phase 2.26: Density-aware sampling with memory-efficient implementation.
        
        Density is estimated as 1 / (1 + average distance to k nearest neighbors).
        Higher density = more neighbors nearby = lower diversity value.
        
        Args:
            features: [N x D] feature tensor
            k: Number of nearest neighbors for density estimation
            
        Returns:
            [N] density values (higher = denser region)
        """
        N = len(features)
        k = min(k, N - 1)
        
        # Normalize features
        features_norm = F.normalize(features, p=2, dim=1)
        
        # Memory-efficient: Always use sampling approach to avoid OOM
        # Sample 1000 reference points for density estimation
        sample_size = min(1000, N)
        sample_indices = torch.randperm(N, device=features.device)[:sample_size]
        features_sample = features_norm[sample_indices]
        
        # Compute distances to sampled points in batches
        batch_size = 5000
        all_knn_distances = []
        
        for i in range(0, N, batch_size):
            batch_end = min(i + batch_size, N)
            batch_features = features_norm[i:batch_end]
            
            # Compute distances to sample points
            cos_sim = torch.mm(batch_features, features_sample.T)
            cos_dist = 1.0 - cos_sim
            
            # Get k nearest distances
            k_actual = min(k, sample_size)
            knn_distances, _ = torch.topk(cos_dist, k=k_actual, dim=1, largest=False)
            all_knn_distances.append(knn_distances)
        
        # Concatenate all batches
        knn_distances = torch.cat(all_knn_distances, dim=0)
        
        # Average k-NN distance
        avg_knn_dist = torch.mean(knn_distances, dim=1)
        
        # Density: 1 / (1 + avg_distance)
        # Higher density = lower avg_distance = higher value
        density = 1.0 / (1.0 + avg_knn_dist)
        
        return density
    
    def _compute_greedy_coreset_indices(self, features: torch.Tensor) -> np.ndarray:
        """Runs probabilistic D² coreset selection (k-means++ style) with cosine distance.
        
        Phase 2.15: Modified to use cosine distance for metric consistency.
        Phase 2.26: Added density-aware sampling.
        
        Key difference from Greedy:
        - Greedy: select_idx = argmax(distances)  # Deterministic
        - D²:     select_idx ~ P(i) ∝ D²(i)      # Probabilistic
        - D² + Density: P(i) ∝ D²(i) × (1 + λ × (1 - density(i)))  # Favor low-density regions
        
        This reduces sensitivity to outliers and improves diversity.
        
        Args:
            features: [NxD] input feature bank to sample.
        """
        number_of_starting_points = np.clip(
            self.number_of_starting_points, None, len(features)
        )
        start_points = np.random.choice(
            len(features), number_of_starting_points, replace=False
        ).tolist()
        
        # Phase 2.26: Compute local density if density_weight > 0
        if self.density_weight > 0:
            local_density = self._compute_local_density(features, k=5)
            # Invert density: favor low-density (diverse) regions
            diversity_factor = 1.0 - local_density  # High diversity = low density
        else:
            diversity_factor = None
        
        # Phase 2.15: Use cosine distance instead of L2
        approximate_distance_matrix = self._compute_cosine_distances(
            features, features[start_points]
        )
        approximate_coreset_anchor_distances = torch.mean(
            approximate_distance_matrix, axis=-1
        ).reshape(-1, 1)
        coreset_indices = []
        num_coreset_samples = int(len(features) * self.percentage)
        
        with torch.no_grad():
            density_desc = f" + Density(λ={self.density_weight})" if self.density_weight > 0 else ""
            for _ in tqdm.tqdm(range(num_coreset_samples), desc=f"Subsampling (D^{self.d2_exponent}{density_desc})..."):
                # Phase 2.15b: Probabilistic selection with adaptive exponent
                # Phase 2.26: P(i) ∝ D^exponent(i) × (1 + λ × diversity(i))
                distances = approximate_coreset_anchor_distances.squeeze()
                
                # Phase 2.17: Enhanced numerical stability fix
                # Clamp distances to avoid negative values from numerical precision
                distances = torch.clamp(distances, min=1e-8, max=2.0)  # Cosine distance ∈ [0, 2]
                
                # Check for invalid distances before power operation
                if torch.isnan(distances).any() or torch.isinf(distances).any():
                    LOGGER.warning(f"Invalid distances detected, using random selection")
                    select_idx = np.random.choice(len(features))
                else:
                    distances_powered = torch.pow(distances, self.d2_exponent)
                    
                    # Phase 2.26: Apply density-aware weighting
                    if diversity_factor is not None:
                        # P(i) ∝ D^exp(i) × (1 + λ × diversity(i))
                        # diversity(i) = 1 - density(i), so low-density regions have higher probability
                        density_modifier = 1.0 + self.density_weight * diversity_factor
                        distances_powered = distances_powered * density_modifier
                    
                    # Avoid division by zero and NaN
                    if distances_powered.sum() < 1e-10 or torch.isnan(distances_powered).any() or torch.isinf(distances_powered).any():
                        # All points are very close or NaN detected, pick randomly
                        select_idx = np.random.choice(len(features))
                    else:
                        # Normalize to probabilities
                        probabilities = distances_powered / (distances_powered.sum() + 1e-10)
                        probabilities = probabilities.cpu().numpy()
                        
                        # Ensure non-negative and valid probabilities
                        probabilities = np.clip(probabilities, 0.0, 1.0)
                        prob_sum = probabilities.sum()
                        
                        # Check for valid probability distribution
                        if np.isnan(probabilities).any() or prob_sum < 1e-6:
                            select_idx = np.random.choice(len(features))
                        else:
                            probabilities = probabilities / prob_sum
                            # Final safety check
                            if np.any(probabilities < 0) or np.isnan(probabilities).any():
                                select_idx = np.random.choice(len(features))
                            else:
                                # Sample according to D^exponent × density distribution
                                select_idx = np.random.choice(len(features), p=probabilities)
                
                coreset_indices.append(select_idx)
                # Phase 2.15: Use cosine distance
                coreset_select_distance = self._compute_cosine_distances(
                    features, features[select_idx : select_idx + 1]  # noqa: E203
                )
                approximate_coreset_anchor_distances = torch.cat(
                    [approximate_coreset_anchor_distances, coreset_select_distance],
                    dim=-1,
                )
                approximate_coreset_anchor_distances = torch.min(
                    approximate_coreset_anchor_distances, dim=1
                ).values.reshape(-1, 1)
        
        return np.array(coreset_indices)


class ClassConditionedIrredundantSampler:
    """
    Class-Conditioned Irredundant Feature Patch Selection (CC-IFPS) Sampler.
    
    This sampler implements a two-stage approach:
    1. Irredundant Filtering: Remove redundant patches using cosine similarity threshold τ
    2. Budget Management: If filtered set exceeds budget, apply D^2 seeding
    
    Key differences from Greedy Coreset:
    - Uses class information for balanced sampling
    - Removes redundant patches (τ-based filtering)
    - Adaptive memory size based on data distribution
    """
    
    def __init__(
        self,
        device: torch.device,
        tau: Union[float, str] = 0.1,
        max_memory_size: int = None,
        percentage: float = None,
        use_d2_seeding: bool = True,
        d2_starting_points: int = 10,
        d2_exponent: float = 2.0,
        use_greedy_approx: bool = False,
        use_anomaly_aware: bool = False,
        use_hybrid: bool = False,
        use_reverse_hybrid: bool = False,
        use_multiscale_density: bool = False,
        class_name: str = None,
        sampling_type: str = 'greedy',
        dimension_to_project_features_to: int = 128,
        use_pca_whitening: bool = False,
        pca_components: int = 128,
    ):
        """
        Args:
            device: torch device for computation
            tau: Threshold for irredundant filtering (cosine distance).
                 Pass 'auto' to estimate tau automatically from the NN distance
                 knee-point: τ_auto ≈ knee(sort(min_{m≠f} d_cos(f, m))).
                 Higher τ = more strict filtering = smaller memory.
            max_memory_size: Maximum number of patches to keep (budget B)
                           If None, uses percentage * total_features
            percentage: Fallback percentage if max_memory_size is None
            use_d2_seeding: Whether to use D^2 seeding for budget management
            d2_starting_points: Number of starting points for D² sampling (Phase 2.15b)
            d2_exponent: Exponent for D² sampling probability (Phase 2.15b)
            use_greedy_approx: Whether to use approximate greedy (10x faster)
            use_anomaly_aware: Whether to use anomaly-aware adaptive τ
            use_hybrid: Whether to use hybrid sampling (Coreset + τ-filtering)
            use_reverse_hybrid: Whether to use reverse hybrid sampling (τ-filtering + Coreset) (Phase 2.3)
            use_multiscale_density: Whether to use multi-scale density adaptive τ (Phase 2)
            class_name: Class name for class-conditional τ scheduling (Phase 2)
            sampling_type: 'greedy' (deterministic) or 'd2' (probabilistic) for Coreset (Phase 2.11)
            dimension_to_project_features_to: Dimension for feature projection
            use_pca_whitening: Apply PCA whitening to features before sampling.
                               Decorrelates dimensions → increases effective cosine distance
                               → improves τ-filtering separation for dense texture classes.
            pca_components: Number of PCA components to keep (128 or 256 recommended).
        """
        self.device = device
        self.tau = tau  # May be float or 'auto'; resolved in run()
        self._tau_auto_resolved = None  # Cache for auto-estimated tau
        self.max_memory_size = max_memory_size
        self.d2_starting_points = d2_starting_points
        self.d2_exponent = d2_exponent
        self.percentage = percentage
        self.use_d2_seeding = use_d2_seeding
        self.use_greedy_approx = use_greedy_approx
        self.use_anomaly_aware = use_anomaly_aware
        self.use_hybrid = use_hybrid
        self.use_reverse_hybrid = use_reverse_hybrid
        self.use_multiscale_density = use_multiscale_density
        self.class_name = class_name
        self.sampling_type = sampling_type
        self.dimension_to_project_features_to = dimension_to_project_features_to
        self.use_pca_whitening = use_pca_whitening
        self.pca_components = pca_components
        self._pca_model = None  # Fitted sklearn PCA model (stored for inference reuse)

        # Phase 2.25: Class-Adaptive Density Weights (Restored for Sampling Optimization)
        # Higher density weight helps in selecting patches from dense regions (irredundant but potentially informative)
        self.class_density_weights = {
            'cable': 0.15,      # 20% -> 35%+ gain targets
            'hazelnut': 0.10,
            'transistor': 0.10,
            'screw': 0.05,
            'toothbrush': 0.05,
        }
        
        # Clean Algorithm 1: No class-specific overrides (Previously)
        # Phase 2.26: Class-Adaptive D2 Exponents (Restored for Optimization)
        # Defines optimal D2 exponents for each class to maximize diversity/stability
        CLASS_D2_EXPONENTS = {
            # Texture (Need high diversity -> Lower exponent for more uniform sampling)
            'grid': 1.6,
            'carpet': 1.7,
            'tile': 1.6,
            'leather': 1.5,
            'wood': 1.7,
            'zipper': 1.8,
            
            # Structural (Need boundary coverage -> Standard/High exponent)
            'transistor': 2.0,
            'metal_nut': 2.0,
            'pill': 2.0,
            'bottle': 2.0,
            
            # Fine-grained (Need outlier robustness -> Lower exponent)
            'screw': 1.4,
            'hazelnut': 1.5,
            'cable': 1.6,
            'toothbrush': 1.3,
            'capsule': 1.5,
        }
        
        if class_name in CLASS_D2_EXPONENTS:
            self.d2_exponent = CLASS_D2_EXPONENTS[class_name]
            LOGGER.info(f"Class-Adaptive D2: Overriding exponent to {self.d2_exponent} for {class_name}")
        else:
            self.d2_exponent = d2_exponent

        # Phase 2.26: Class-Adaptive Hybrid Ratio table
        # (Stage1_ratio, Stage2_ratio) — Stage1 = Coreset budget fraction
        self.class_hybrid_ratios = {
            # Texture — τ-filtering 효과적 → Stage2 비율 높임
            'grid':     (0.60, 0.40),
            'tile':     (0.60, 0.40),
            'carpet':   (0.65, 0.35),
            'leather':  (0.65, 0.35),
            'wood':     (0.70, 0.30),
            'zipper':   (0.70, 0.30),
            # Structural — Coreset 중심
            'transistor': (0.70, 0.30),  # 85→70 (low utilization class)
            'metal_nut':  (0.85, 0.15),
            'pill':       (0.85, 0.15),
            'bottle':     (0.85, 0.15),
            # Fine-grained — 균형
            'screw':      (0.75, 0.25),
            'toothbrush': (0.75, 0.25),
            'hazelnut':   (0.65, 0.35),  # 80→65 (low utilization class)
            'cable':      (0.65, 0.35),  # 80→65 (low utilization class)
            'capsule':    (0.80, 0.20),
        }

        LOGGER.info(
            f"ClassConditionedIrredundantSampler initialized (Algorithm 1 + Adaptive D2): "
            f"tau={tau}, max_memory_size={max_memory_size}, "
            f"use_hybrid={use_hybrid}, class_name={class_name}, d2_exponent={self.d2_exponent}, "
            f"use_pca_whitening={use_pca_whitening}(components={pca_components})"
        )

    # =========================================================================
    # NEW: Adaptive τ Auto-Estimation
    # =========================================================================

    def estimate_tau_auto(
        self,
        features: torch.Tensor,
        sample_size: int = 5000,
        percentile: float = 50.0,
        tau_min: float = 0.005,
        tau_max: float = 0.040,
    ) -> float:
        """
        Estimate irredundancy threshold τ automatically from the NN distance
        distribution of the feature bank.

        Algorithm (percentile-based, v2):
            τ_auto = clamp(P_{percentile}(1-NN cosine distances), tau_min, tau_max)

        The previous 2nd-derivative knee method always peaked at the
        distribution tail (idx ≈ N), making it degenerate for smooth
        distributions. The median (P50) NN distance is a robust proxy
        for feature density and better correlates with the optimal τ.

        Args:
            features:    [N x D] tensor (raw or L2-normalised, on any device).
            sample_size: Number of patches to sub-sample for estimation.
            percentile:  Which percentile of NN distances to use as τ (default: 50).
            tau_min:     Lower clamp bound (default 0.005).
            tau_max:     Upper clamp bound (default 0.040).

        Returns:
            Estimated τ as a float.
        """
        N = len(features)
        # Work on CPU with float32 to avoid OOM on large banks
        feats = features.float().cpu()
        feats_norm = F.normalize(feats, p=2, dim=1)  # L2-normalise

        # Sub-sample
        if N > sample_size:
            idx = torch.randperm(N)[:sample_size]
            feats_norm = feats_norm[idx]

        n = len(feats_norm)
        nn_distances = torch.zeros(n)

        # Compute 1-NN cosine distance in batches (avoid O(n²) memory)
        batch_size = min(1000, n)
        for start in range(0, n, batch_size):
            end = min(start + batch_size, n)
            batch = feats_norm[start:end]  # [B x D]
            sim = torch.mm(batch, feats_norm.T)  # [B x n]
            for bi, gi in enumerate(range(start, end)):
                sim[bi, gi] = -float('inf')  # exclude self
            cos_dist = 1.0 - sim
            nn_distances[start:end] = torch.min(cos_dist, dim=1).values

        # ── Percentile-based estimation ───────────────────────────────────────
        p25 = float(torch.quantile(nn_distances, 0.25).item())
        p50 = float(torch.quantile(nn_distances, 0.50).item())
        p75 = float(torch.quantile(nn_distances, 0.75).item())
        p95 = float(torch.quantile(nn_distances, 0.95).item())

        LOGGER.info(
            f"[τ_auto debug] NN dist percentiles: "
            f"25%={p25:.4f}  50%={p50:.4f}  75%={p75:.4f}  95%={p95:.4f}"
        )

        tau_raw = float(torch.quantile(nn_distances, percentile / 100.0).item())
        tau_est = max(tau_min, min(tau_max, tau_raw))

        LOGGER.info(
            f"[τ_auto] class={self.class_name}: "
            f"P{percentile:.0f}={tau_raw:.4f} → clamped={tau_est:.4f} "
            f"(range=[{tau_min}, {tau_max}])"
        )
        return tau_est

    # =========================================================================
    # NEW: Memory Bank Quality Score (MBQS)
    # =========================================================================

    def evaluate_memory_quality(
        self,
        memory: torch.Tensor,
        full_features: torch.Tensor,
        pair_sample: int = 5000,
    ) -> float:
        """
        Compute the Memory Bank Quality Score (MBQS) for a given memory bank.

        MBQS = Coverage × Dispersion / (1 + Redundancy)

        Definitions:
          Coverage   = fraction of full_features whose nearest memory patch
                       is within ε = median(memory NN distances).
          Dispersion = mean pairwise cosine distance within memory
                       (estimated from `pair_sample` random pairs).
          Redundancy = fraction of random pair_sample pairs in memory
                       that have cosine distance < τ/2.

        Args:
            memory: [M x D] tensor — the constructed memory bank.
            full_features: [N x D] tensor — all training features.
            pair_sample: Number of random pairs used for Dispersion and
                         Redundancy estimation.

        Returns:
            MBQS as a float (higher is better).
        """
        # Work on CPU with float32
        mem  = F.normalize(memory.float().cpu(), p=2, dim=1)  # [M x D]
        full = F.normalize(full_features.float().cpu(), p=2, dim=1)  # [N x D]
        M = len(mem)
        N = len(full)

        # --- ε = median NN distance within memory ---
        batch = min(1000, M)
        mem_nn_dists = []
        for s in range(0, M, batch):
            e = min(s + batch, M)
            b = mem[s:e]  # [b x D]
            sim = torch.mm(b, mem.T)  # [b x M]
            for bi, gi in enumerate(range(s, e)):
                sim[bi, gi] = -float('inf')
            d = 1.0 - sim
            mem_nn_dists.append(torch.min(d, dim=1).values)
        mem_nn_dists = torch.cat(mem_nn_dists)
        epsilon = float(torch.median(mem_nn_dists).item())

        # --- Coverage: fraction of full_features within ε of memory ---
        covered = 0
        batch_n = min(2000, N)
        sample_full_idx = torch.randperm(N)[:min(N, 10000)]
        sample_full = full[sample_full_idx]
        for s in range(0, len(sample_full), batch_n):
            e = min(s + batch_n, len(sample_full))
            b = sample_full[s:e]  # [b x D]
            sim = torch.mm(b, mem.T)  # [b x M]
            min_dist = (1.0 - torch.max(sim, dim=1).values)  # cosine dist to nearest memory
            covered += int((min_dist <= epsilon).sum().item())
        coverage = covered / len(sample_full) if len(sample_full) > 0 else 0.0

        # --- Dispersion & Redundancy from random pairs in memory ---
        n_pairs = min(pair_sample, M * (M - 1) // 2)
        idx_a = torch.randint(0, M, (n_pairs,))
        idx_b = torch.randint(0, M, (n_pairs,))
        # Avoid self-pairs
        mask = idx_a != idx_b
        idx_a, idx_b = idx_a[mask], idx_b[mask]
        if len(idx_a) == 0:
            dispersion = 0.0
            redundancy = 0.0
        else:
            pair_cos_sim = (mem[idx_a] * mem[idx_b]).sum(dim=1)  # dot after L2-norm
            pair_cos_dist = 1.0 - pair_cos_sim
            dispersion = float(pair_cos_dist.mean().item())
            tau_val = self._tau_auto_resolved if self._tau_auto_resolved is not None else (
                self.tau if isinstance(self.tau, float) else 0.02
            )
            redundancy = float((pair_cos_dist < tau_val / 2.0).float().mean().item())

        # Phase 2.27: MBQS_v2 = Coverage^2 * Dispersion / (1 + Redundancy)
        # alpha=2, beta=1 to favor coverage which correlates better with Pixel AP.
        # Plus a penalty for very small bank sizes (< 1000).
        mbqs = (coverage**2 * dispersion) / (1.0 + redundancy)
        
        # Small bank size penalty
        if M < 1000:
            mbqs *= (M / 1000.0)

        LOGGER.info(
            f"[MBQS] class={self.class_name}: "
            f"coverage={coverage:.3f}, dispersion={dispersion:.4f}, "
            f"redundancy={redundancy:.4f}, size_penalty={min(1.0, M/1000.0):.2f} → MBQS={mbqs:.4f}"
        )
        return mbqs

    # =========================================================================
    # NEW: PCA Whitening
    # =========================================================================

    def apply_pca_whitening(
        self,
        features: torch.Tensor,
        n_components: Optional[int] = None,
    ) -> torch.Tensor:
        """
        Apply PCA whitening to decorrelate feature dimensions.

        Effect: correlated WideResNet50 feature dimensions are removed →
        effective cosine distances between patches increase → τ-filtering
        becomes more discriminative for dense-texture classes (carpet, grid).

        Fits a sklearn PCA model on the first call and reuses it for
        subsequent calls (e.g., during inference).

        Args:
            features: [N x D] tensor.
            n_components: PCA components to keep. Defaults to self.pca_components.

        Returns:
            Whitened features as a [N x n_components] torch.Tensor.

        Raises:
            RuntimeError if sklearn is not installed.
        """
        if not _SKLEARN_AVAILABLE:
            raise RuntimeError(
                "sklearn is required for PCA whitening: `pip install scikit-learn`"
            )
        n_components = n_components if n_components is not None else self.pca_components

        feats_np = features.float().cpu().numpy()

        if self._pca_model is None:
            LOGGER.info(
                f"[PCA] Fitting PCA(n_components={n_components}, whiten=True) "
                f"on {feats_np.shape[0]} features of dim {feats_np.shape[1]}"
            )
            self._pca_model = SklearnPCA(n_components=n_components, whiten=True)
            self._pca_model.fit(feats_np)
            explained = self._pca_model.explained_variance_ratio_.sum()
            LOGGER.info(f"[PCA] Explained variance ratio (top-{n_components}): {explained:.3f}")

        whitened = self._pca_model.transform(feats_np)
        return torch.from_numpy(whitened).float()
    
    def run(
        self, features: Union[torch.Tensor, np.ndarray]
    ) -> Union[torch.Tensor, np.ndarray]:
        """
        Main sampling method.
        
        Args:
            features: [N x D] feature tensor
            
        Returns:
            Sampled features and their corresponding selection weights (D2 distance)
        """
        # Phase 3: Return weights for density-aware scoring
        return_weights = True

        # Store original type
        features_is_numpy = isinstance(features, np.ndarray)
        if features_is_numpy:
            features_device = None
            features = torch.from_numpy(features)
        else:
            features_device = features.device

        features = features.to(self.device)

        # ── PCA Whitening (optional pre-processing) ───────────────────────
        if self.use_pca_whitening:
            features_whitened = self.apply_pca_whitening(features, n_components=self.pca_components)
            features = features_whitened.to(self.device)
            LOGGER.info(f"[PCA] Features whitened: {features.shape}")

        # ── Adaptive τ: estimate from feature distribution if tau='auto' ──
        if isinstance(self.tau, str) and self.tau == 'auto':
            estimated = self.estimate_tau_auto(features)
            self._tau_auto_resolved = estimated
            # Temporarily set self.tau so downstream methods use the real value
            self.tau = estimated
            LOGGER.info(f"[τ_auto] Resolved τ = {self.tau:.4f} for class={self.class_name}")
        else:
            self._tau_auto_resolved = float(self.tau)

        # Determine budget
        if self.max_memory_size is None:
            if self.percentage is not None:
                budget = int(len(features) * self.percentage)
            else:
                budget = len(features)  # No budget limit
        else:
            budget = self.max_memory_size

        LOGGER.info(
            f"Starting CC-IFPS: {len(features)} patches, budget={budget}, tau={self.tau}"
        )
        
        # Algorithm 1: Hybrid mode only (Coreset + τ-filtering with immediate τ-check)
        # Note: Phase 2 features (reverse_hybrid, anomaly_aware, etc.) are disabled
        if self.use_hybrid:
            final_features, final_weights = self._hybrid_sampling(features, budget, sampling_type=self.sampling_type)
        else:
            # Fallback: Sequential irredundant filtering (not used in Algorithm 1)
            # This branch should not be reached with current configuration
            LOGGER.warning("use_hybrid=False: Using sequential filtering (not Algorithm 1)")
            if self.use_greedy_approx:
                irredundant_indices = self._irredundant_filtering_approx(features)
            else:
                irredundant_indices = self._irredundant_filtering_sequential(features)
            irredundant_features = features[irredundant_indices]
            
            # Budget management
            if len(irredundant_features) > budget:
                if self.use_d2_seeding:
                    final_indices, final_weights = self._d2_seeding(
                        irredundant_features, budget, class_name=self.class_name
                    )
                else:
                    final_indices = np.random.choice(
                        len(irredundant_features), budget, replace=False
                    )
                    final_weights = np.ones(len(final_indices), dtype=np.float32)
                final_features = irredundant_features[final_indices]
            else:
                final_features = irredundant_features
                final_weights = np.ones(len(final_features), dtype=np.float32)
        
        LOGGER.info(f"Final memory size: {len(final_features)} patches")
        
        
        # Restore original type
        if features_is_numpy:
            return final_features.cpu().numpy(), final_weights
        else:
            return final_features.to(features_device), final_weights
    
    def _irredundant_filtering(self, features: torch.Tensor) -> np.ndarray:
        """
        Stage 1: Greedy Irredundant Filtering using cosine distance threshold.
        
        Greedy selection algorithm:
        1. Select first patch deterministically (max feature norm)
        2. While candidates remain:
           - For each remaining patch, compute min distance to selected set M
           - Filter patches where min_distance > τ (valid candidates)
           - Among valid candidates, select the one with MAXIMUM distance (Greedy)
           - Add to M and repeat
        
        This combines:
        - Greedy Coreset's coverage optimization (always pick farthest)
        - τ-filtering's redundancy removal (only consider patches with dist > τ)
        
        Args:
            features: [N x D] feature tensor
            
        Returns:
            Indices of selected irredundant patches
        """
        N = len(features)
        selected_indices = []
        remaining_indices = list(range(N))
        
        # Normalize features for cosine similarity
        features_norm = F.normalize(features, p=2, dim=1)
        
        # Select first patch deterministically: farthest from center in cosine space
        # Center in cosine space = mean direction
        center = torch.mean(features_norm, dim=0, keepdim=True)  # [1 x D]
        center_norm = F.normalize(center, p=2, dim=1)  # Normalize center direction
        
        # Cosine distance from center
        cos_sim_to_center = torch.mm(features_norm, center_norm.T).squeeze()  # [N]
        cos_dist_to_center = 1.0 - cos_sim_to_center  # [N]
        
        # Select patch farthest from center (most outlier in cosine space)
        first_idx = torch.argmax(cos_dist_to_center).item()
        selected_indices.append(first_idx)
        remaining_indices.remove(first_idx)
        
        # Batch processing to avoid OOM
        batch_size = 10000  # Process 10k patches at a time
        
        with torch.no_grad():
            with tqdm.tqdm(total=N, desc="Greedy irredundant filtering") as pbar:
                pbar.update(1)  # First patch
                
                while len(remaining_indices) > 0:
                    selected_features = features_norm[selected_indices]  # [M x D]
                    
                    # Process remaining patches in batches to avoid OOM
                    min_distances_all = []
                    for batch_start in range(0, len(remaining_indices), batch_size):
                        batch_end = min(batch_start + batch_size, len(remaining_indices))
                        batch_indices = remaining_indices[batch_start:batch_end]
                        
                        # Compute distances for this batch
                        batch_features = features_norm[batch_indices]  # [B x D]
                        
                        # Cosine similarity: [B x M]
                        cos_sim = torch.mm(batch_features, selected_features.T)
                        
                        # Cosine distance: 1 - cos(f_i, m)
                        cos_dist = 1.0 - cos_sim  # [B x M]
                        
                        # Minimum distance for each patch in batch
                        batch_min_distances = torch.min(cos_dist, dim=1).values  # [B]
                        min_distances_all.append(batch_min_distances)
                    
                    # Concatenate all batch results
                    min_distances = torch.cat(min_distances_all)  # [R]
                    
                    # Filter: only consider patches with min_distance > τ
                    valid_mask = min_distances > self.tau
                    
                    if valid_mask.sum() == 0:
                        # No more valid candidates
                        break
                    
                    # Greedy: among valid candidates, select the one with MAXIMUM distance
                    valid_indices = torch.where(valid_mask)[0]
                    valid_distances = min_distances[valid_indices]
                    best_local_idx = torch.argmax(valid_distances).item()
                    best_global_idx = remaining_indices[valid_indices[best_local_idx].item()]
                    
                    selected_indices.append(best_global_idx)
                    remaining_indices.remove(best_global_idx)
                    
                    pbar.update(1)
                    if len(selected_indices) % 100 == 0:
                        pbar.set_postfix({"selected": len(selected_indices)})
        
        return np.array(selected_indices)
    
    def _irredundant_filtering_approx(self, features: torch.Tensor) -> np.ndarray:
        """
        Stage 1: Approximate Greedy Irredundant Filtering (10x faster).
        
        Approximate greedy selection:
        1. Select first patch deterministically (farthest from center in cosine space)
        2. Use 10% random subset as anchor candidates
        3. While candidates remain:
           - Compute min distance only for anchor subset
           - Filter anchors where min_distance > τ
           - Among valid anchors, select the one with MAXIMUM distance (Greedy)
           - Add to M and repeat
        
        Time complexity: O(N × M × 0.1) ≈ 10x faster than full greedy
        
        Args:
            features: [N x D] feature tensor
            
        Returns:
            Indices of selected irredundant patches
        """
        N = len(features)
        selected_indices = []
        
        # Normalize features for cosine similarity
        features_norm = F.normalize(features, p=2, dim=1)
        
        # Select first patch deterministically: farthest from center in cosine space
        center = torch.mean(features_norm, dim=0, keepdim=True)  # [1 x D]
        center_norm = F.normalize(center, p=2, dim=1)
        cos_sim_to_center = torch.mm(features_norm, center_norm.T).squeeze()  # [N]
        cos_dist_to_center = 1.0 - cos_sim_to_center  # [N]
        first_idx = torch.argmax(cos_dist_to_center).item()
        selected_indices.append(first_idx)
        
        # Create anchor subset (10% of N)
        anchor_size = max(int(N * 0.1), 1000)  # At least 1000 anchors
        anchor_size = min(anchor_size, N - 1)  # Don't exceed N-1
        
        # Random sample anchors (excluding first_idx)
        remaining_pool = list(range(N))
        remaining_pool.remove(first_idx)
        anchor_indices = np.random.choice(remaining_pool, anchor_size, replace=False).tolist()
        
        # Batch processing to avoid OOM
        batch_size = 10000
        
        with torch.no_grad():
            with tqdm.tqdm(total=anchor_size, desc="Approximate greedy irredundant filtering") as pbar:
                pbar.update(0)  # First patch already selected
                
                while len(anchor_indices) > 0:
                    selected_features = features_norm[selected_indices]  # [M x D]
                    
                    # Process anchor patches in batches
                    min_distances_all = []
                    for batch_start in range(0, len(anchor_indices), batch_size):
                        batch_end = min(batch_start + batch_size, len(anchor_indices))
                        batch_anchor_indices = anchor_indices[batch_start:batch_end]
                        
                        # Compute distances for this batch of anchors
                        batch_features = features_norm[batch_anchor_indices]  # [B x D]
                        
                        # Cosine similarity: [B x M]
                        cos_sim = torch.mm(batch_features, selected_features.T)
                        
                        # Cosine distance: 1 - cos(f_i, m)
                        cos_dist = 1.0 - cos_sim  # [B x M]
                        
                        # Minimum distance for each patch in batch
                        batch_min_distances = torch.min(cos_dist, dim=1).values  # [B]
                        min_distances_all.append(batch_min_distances)
                    
                    # Concatenate all batch results
                    min_distances = torch.cat(min_distances_all)  # [A] where A = len(anchor_indices)
                    
                    # Filter: only consider patches with min_distance > τ
                    valid_mask = min_distances > self.tau
                    
                    if valid_mask.sum() == 0:
                        # No more valid candidates
                        break
                    
                    # Greedy: among valid anchors, select the one with MAXIMUM distance
                    valid_indices = torch.where(valid_mask)[0]
                    valid_distances = min_distances[valid_indices]
                    best_local_idx = torch.argmax(valid_distances).item()
                    best_global_idx = anchor_indices[valid_indices[best_local_idx].item()]
                    
                    selected_indices.append(best_global_idx)
                    anchor_indices.remove(best_global_idx)
                    
                    pbar.update(1)
                    if len(selected_indices) % 100 == 0:
                        pbar.set_postfix({"selected": len(selected_indices)})
        
        return np.array(selected_indices)
    
    def _anomaly_aware_filtering(self, features: torch.Tensor) -> np.ndarray:
        """
        Stage 1: Anomaly-Aware Irredundant Filtering with Adaptive τ.
        
        핵심 아이디어:
        - Outlier 패치 (anomaly 가능성 높음): 낮은 τ → 더 많이 보존
        - Normal 패치 (중심 근처): 높은 τ → 더 많이 필터링
        
        이를 통해 anomaly detection에 중요한 패치를 더 많이 보존하여
        Pixel AP를 개선합니다.
        
        Args:
            features: [N x D] feature tensor
            
        Returns:
            Indices of selected irredundant patches
        """
        N = len(features)
        selected_indices = []
        
        # Normalize features for cosine similarity
        features_norm = F.normalize(features, p=2, dim=1)
        
        # 1. Compute outlier scores (distance from center)
        # Outlier = anomaly 가능성이 높은 패치
        center = torch.mean(features_norm, dim=0, keepdim=True)  # [1 x D]
        center_norm = F.normalize(center, p=2, dim=1)
        
        # Cosine distance from center
        cos_sim_to_center = torch.mm(features_norm, center_norm.T).squeeze()  # [N]
        outlier_scores = 1.0 - cos_sim_to_center  # [N]
        
        # 2. Compute adaptive τ for each patch
        tau_base = self.tau
        tau_min = tau_base * 0.3  # Outlier용 (더 낮은 τ = 더 많이 보존)
        tau_max = tau_base * 1.5  # Normal용 (더 높은 τ = 더 많이 필터링)
        
        # Normalize outlier scores to [0, 1]
        outlier_min = outlier_scores.min()
        outlier_max = outlier_scores.max()
        outlier_normalized = (outlier_scores - outlier_min) / (outlier_max - outlier_min + 1e-8)
        
        # Adaptive τ: High outlier score → Low τ
        adaptive_tau = tau_max - outlier_normalized * (tau_max - tau_min)
        
        # 3. Select first patch (highest outlier score = most anomalous)
        first_idx = torch.argmax(outlier_scores).item()
        selected_indices.append(first_idx)
        
        LOGGER.info(
            f"Anomaly-aware filtering: τ range [{tau_min:.4f}, {tau_max:.4f}], "
            f"outlier score range [{outlier_min:.4f}, {outlier_max:.4f}]"
        )
        
        # 4. Sequential filtering with adaptive τ
        with torch.no_grad():
            with tqdm.tqdm(total=N-1, desc="Anomaly-aware filtering") as pbar:
                for i in range(N):
                    if i == first_idx:
                        continue
                    
                    # Compute min distance to selected patches
                    current_feature = features_norm[i:i+1]  # [1 x D]
                    selected_features = features_norm[selected_indices]  # [M x D]
                    
                    # Cosine similarity
                    cos_sim = torch.mm(current_feature, selected_features.T)  # [1 x M]
                    
                    # Cosine distance
                    cos_dist = 1.0 - cos_sim  # [1 x M]
                    
                    # Minimum distance
                    min_distance = torch.min(cos_dist).item()
                    
                    # Use adaptive τ for this patch
                    if min_distance > adaptive_tau[i]:
                        selected_indices.append(i)
                    
                    pbar.update(1)
                    if (i + 1) % 1000 == 0:
                        pbar.set_postfix({"selected": len(selected_indices)})
        
        LOGGER.info(
            f"Anomaly-aware filtering: {len(selected_indices)} patches selected "
            f"({100*len(selected_indices)/N:.1f}% of original)"
        )
        
        return np.array(selected_indices)
    
    def _irredundant_filtering_sequential(self, features: torch.Tensor) -> np.ndarray:
        """
        Stage 1: Sequential Irredundant Filtering (original method).
        
        Sequential selection algorithm:
        1. Select first patch deterministically (farthest from center in cosine space)
        2. For each remaining feature f_i (in order):
           - Compute s(f_i, M) = min_{m ∈ M} (1 - cos(f_i, m))
           - If s(f_i, M) > τ, add f_i (sufficiently novel)
           - Else, skip f_i (redundant)
        
        Args:
            features: [N x D] feature tensor
            
        Returns:
            Indices of selected irredundant patches
        """
        N = len(features)
        selected_indices = []
        
        # Normalize features for cosine similarity
        features_norm = F.normalize(features, p=2, dim=1)
        
        # Select first patch deterministically: farthest from center in cosine space
        center = torch.mean(features_norm, dim=0, keepdim=True)  # [1 x D]
        center_norm = F.normalize(center, p=2, dim=1)
        cos_sim_to_center = torch.mm(features_norm, center_norm.T).squeeze()  # [N]
        cos_dist_to_center = 1.0 - cos_sim_to_center  # [N]
        first_idx = torch.argmax(cos_dist_to_center).item()
        selected_indices.append(first_idx)
        
        with torch.no_grad():
            with tqdm.tqdm(total=N-1, desc="Sequential irredundant filtering") as pbar:
                for i in range(N):
                    if i == first_idx:
                        continue  # Skip first patch (already selected)
                    
                    # Compute cosine similarity with all selected patches
                    current_feature = features_norm[i:i+1]  # [1 x D]
                    selected_features = features_norm[selected_indices]  # [M x D]
                    
                    # Cosine similarity: cos(f_i, m) = f_i · m (already normalized)
                    cos_sim = torch.mm(current_feature, selected_features.T)  # [1 x M]
                    
                    # Cosine distance: 1 - cos(f_i, m)
                    cos_dist = 1.0 - cos_sim  # [1 x M]
                    
                    # Minimum distance to any selected patch
                    min_dist = torch.min(cos_dist).item()
                    
                    # Add if sufficiently novel
                    if min_dist > self.tau:
                        selected_indices.append(i)
                    
                    pbar.update(1)
                    if (i + 1) % 1000 == 0:
                        pbar.set_postfix({"selected": len(selected_indices)})
        
        return np.array(selected_indices)
    
    def _compute_multiscale_density(self, features_norm: torch.Tensor, k_values: list = [3, 5, 9, 15]) -> torch.Tensor:
        """
        Phase 2.1 기능 1: Multi-scale density 계산 (Optimized k values)
        
        여러 k 값으로 local density를 계산하고 평균을 취함.
        ✅ OPTIMIZED: k = [3, 5, 9, 15] (이전: [5, 10, 20, 50])
        - 메모리 크기가 ~6000개로 줄었으므로 더 local한 k 값 사용
        - k=50은 전체의 8.3%로 너무 넓어 변별력 저하
        
        Dense 영역 (많은 이웃) → 높은 density → 높은 τ (더 많이 필터링)
        Sparse 영역 (적은 이웃) → 낮은 density → 낮은 τ (더 많이 보존)
        
        Args:
            features_norm: [N x D] normalized features
            k_values: List of k values for multi-scale density
            
        Returns:
            density_scores: [N] density score for each patch (0~1)
        """
        N = len(features_norm)
        device = features_norm.device
        
        # Compute pairwise cosine distances
        cos_sim = torch.mm(features_norm, features_norm.T)  # [N x N]
        cos_dist = 1.0 - cos_sim  # [N x N]
        
        # For each k, compute average distance to k-nearest neighbors
        density_scores_list = []
        
        for k in k_values:
            k_actual = min(k, N - 1)  # Handle small N
            
            # Get k-nearest distances for each patch
            k_nearest_dists, _ = torch.topk(cos_dist, k_actual + 1, dim=1, largest=False)
            # Exclude self (distance 0)
            k_nearest_dists = k_nearest_dists[:, 1:]  # [N x k]
            
            # Average distance to k-nearest neighbors
            avg_k_dist = torch.mean(k_nearest_dists, dim=1)  # [N]
            
            # Convert to density: higher distance → lower density
            # Normalize to [0, 1]
            density_k = 1.0 - (avg_k_dist - avg_k_dist.min()) / (avg_k_dist.max() - avg_k_dist.min() + 1e-8)
            density_scores_list.append(density_k)
        
        # Average across all scales
        density_scores = torch.stack(density_scores_list).mean(dim=0)  # [N]
        
        return density_scores
    
    def _hybrid_sampling(self, features: torch.Tensor, budget: int, sampling_type: str = 'greedy') -> Tuple[torch.Tensor, np.ndarray]:
        """
        Hybrid Sampling: Two-Stage (Coreset + τ-filtering)
        Restored from thesis implementation (Phase 2.26).

        Stage 1: Coreset (Greedy or D²) → Coverage 최적화 (70% of budget)
        Stage 2: Sequential τ-filtering → Redundancy 제거 (remaining 30%)

        τ에 의해 실제 bank size가 budget보다 훨씬 작아짐 (논문 평균 13K).

        Args:
            features: [N x D] feature tensor
            budget: Total budget (B), used as hard upper bound
            sampling_type: 'greedy' or 'd2'

        Returns:
            (final_features [M x D], weights [M])
        """
        N = len(features)

        # Class-Adaptive Hybrid Ratio
        if self.class_name and hasattr(self, 'class_hybrid_ratios') and self.class_name in self.class_hybrid_ratios:
            stage1_ratio, _ = self.class_hybrid_ratios[self.class_name]
            LOGGER.info(f"Hybrid: {self.class_name} → Stage1={stage1_ratio*100:.0f}%")
        else:
            stage1_ratio = 0.70
            LOGGER.info(f"Hybrid: {self.class_name or 'unknown'} (default) → Stage1=70%, Stage2=30%")

        # ── Stage 1: Coreset ──────────────────────────────────────────────────
        stage1_budget = int(budget * stage1_ratio)

        if stage1_budget >= N:
            LOGGER.warning(f"Stage1 budget ({stage1_budget}) >= N ({N}). Using all features.")
            stage1_features = features
        else:
            if sampling_type == 'd2':
                LOGGER.info(f"Hybrid Stage 1: Probabilistic D² Coreset ({stage1_budget} patches)")
                d2_exp       = self.class_d2_exponents.get(self.class_name, self.d2_exponent) \
                               if (self.class_name and hasattr(self, 'class_d2_exponents')) else self.d2_exponent
                starting_pts = self.class_starting_points.get(self.class_name, self.d2_starting_points) \
                               if (self.class_name and hasattr(self, 'class_starting_points')) else self.d2_starting_points
                density_wt   = self.class_density_weights.get(self.class_name, 0.0) \
                               if (self.class_name and hasattr(self, 'class_density_weights')) else 0.0

                coreset_sampler = ProbabilisticCoresetSampler(
                    percentage=stage1_budget / N,
                    device=self.device,
                    number_of_starting_points=starting_pts,
                    dimension_to_project_features_to=self.dimension_to_project_features_to,
                    d2_exponent=d2_exp,
                    density_weight=density_wt,
                )
            else:
                LOGGER.info(f"Hybrid Stage 1: Approximate Greedy Coreset ({stage1_budget} patches)")
                coreset_sampler = ApproximateGreedyCoresetSampler(
                    percentage=stage1_budget / N,
                    device=self.device,
                    dimension_to_project_features_to=self.dimension_to_project_features_to,
                )

            stage1_features = coreset_sampler.run(features)

        LOGGER.info(
            f"Stage 1 complete: {len(stage1_features)} patches "
            f"({100*len(stage1_features)/N:.1f}% of original)"
        )

        # ── Stage 2: Sequential τ-filtering ──────────────────────────────────
        stage2_budget = budget - len(stage1_features)

        # Class-conditional τ multiplier
        tau_base = self.tau
        if self.class_name and hasattr(self, 'class_tau_multipliers') \
                and self.class_name in self.class_tau_multipliers:
            tau_multiplier = self.class_tau_multipliers[self.class_name]
            tau_base = self.tau * tau_multiplier
            LOGGER.info(f"Class-conditional τ: {self.class_name} → τ={tau_base:.4f} (×{tau_multiplier})")

        LOGGER.info(f"Hybrid Stage 2: Sequential τ-filtering (budget={stage2_budget}, τ={tau_base:.4f})")

        # Normalize for cosine distance
        features_norm = F.normalize(stage1_features, p=2, dim=1)

        # Multi-scale density adaptive τ (optional)
        adaptive_tau = None
        if hasattr(self, 'use_multiscale_density') and self.use_multiscale_density:
            LOGGER.info("Computing multi-scale density for adaptive τ...")
            density_scores = self._compute_multiscale_density(features_norm)
            tau_min_val = tau_base * 0.5
            tau_max_val = tau_base * 1.5
            adaptive_tau = tau_min_val + density_scores * (tau_max_val - tau_min_val)
            LOGGER.info(f"Adaptive τ range: [{tau_min_val:.4f}, {tau_max_val:.4f}]")

        # Random shuffle to prevent data-order bias
        perm = torch.randperm(len(stage1_features), device=features_norm.device)
        features_norm_shuffled = features_norm[perm]
        adaptive_tau_shuffled = adaptive_tau[perm] if adaptive_tau is not None else None

        # First patch: farthest from centroid (deterministic)
        center = torch.mean(features_norm_shuffled, dim=0, keepdim=True)
        center_norm = F.normalize(center, p=2, dim=1)
        cos_dist_to_center = 1.0 - torch.mm(features_norm_shuffled, center_norm.T).squeeze()
        first_idx = torch.argmax(cos_dist_to_center).item()
        selected_indices_shuffled = [first_idx]

        # Sequential τ-filtering with Hierarchical τ + Adaptive τ (v2.29)
        tau_current = tau_base  # mutable copy for adaptive adjustment
        with torch.no_grad():
            with tqdm.tqdm(total=len(stage1_features)-1, desc="Hybrid Stage 2: τ-filtering") as pbar:
                for i in range(len(stage1_features)):
                    if i == first_idx:
                        continue
                    curr = features_norm_shuffled[i:i+1]
                    sel  = features_norm_shuffled[selected_indices_shuffled]
                    min_distance = torch.min(1.0 - torch.mm(curr, sel.T)).item()

                    # ── Hierarchical τ Scheduling ──────────────────────
                    # Relax τ progressively as Stage 2 progresses
                    accepted_count = len(selected_indices_shuffled)
                    progress = accepted_count / max(stage2_budget, 1)
                    if progress < 0.5:
                        tau_factor = 1.0    # first 50%: strict
                    elif progress < 0.8:
                        tau_factor = 0.85   # next 30%: moderate relaxation
                    else:
                        tau_factor = 0.70   # last 20%: aggressive relaxation

                    tau_thr = adaptive_tau_shuffled[i].item() \
                              if adaptive_tau_shuffled is not None else (tau_current * tau_factor)

                    if min_distance > tau_thr:
                        selected_indices_shuffled.append(i)

                    pbar.update(1)

                    # ── Adaptive τ Strengthening (every 500 patches) ──
                    if (i + 1) % 500 == 0:
                        current_util = len(selected_indices_shuffled) / max(stage2_budget, 1)
                        expected_util = (i + 1) / len(stage1_features)
                        pbar.set_postfix({
                            "selected": len(selected_indices_shuffled),
                            "util": f"{current_util:.1%}",
                            "τ": f"{tau_current:.4f}",
                        })
                        # If actual utilization is far below expected → reduce τ
                        if current_util < expected_util * 0.5:
                            tau_current *= 0.88  # 12% reduction
                            LOGGER.info(
                                f"Adaptive τ: low util ({current_util:.1%} vs "
                                f"expected {expected_util:.1%}), τ → {tau_current:.4f}"
                            )

                    # Hard budget cap
                    if len(selected_indices_shuffled) >= stage2_budget:
                        break

        # Map back to original indices
        original_indices = perm[selected_indices_shuffled].cpu().numpy()
        stage2_features  = stage1_features[original_indices]

        LOGGER.info(
            f"Stage 2 complete: {len(stage2_features)} patches "
            f"({100*len(stage2_features)/len(stage1_features):.1f}% of Stage 1)"
        )

        # Final budget guard (should rarely trigger)
        if len(stage2_features) > budget:
            LOGGER.info(f"Final budget trim: {len(stage2_features)} → {budget}")
            rnd_idx = np.random.choice(len(stage2_features), budget, replace=False)
            final_features = stage2_features[rnd_idx]
        else:
            final_features = stage2_features

        LOGGER.info(
            f"Hybrid sampling complete: {len(final_features)} patches "
            f"(utilization={100*len(final_features)/budget:.1f}% of budget={budget})"
        )

        # Weights: distance-to-nearest-selected for each patch (proxy for importance)
        weights = cos_dist_to_center[perm[selected_indices_shuffled[:len(final_features)]]].cpu().numpy()

        return final_features, weights

    def _reverse_hybrid_sampling(self, features: torch.Tensor, budget: int) -> torch.Tensor:
        """
        Reverse Hybrid Sampling (Phase 2.3): τ-filtering → Greedy Coreset
        
        핵심 아이디어:
        - Stage 1: Adaptive τ-filtering (전체 패치에서 중복 제거 = Denoising)
        - Stage 2: Approximate Greedy Coreset (정제된 후보군에서 coverage 최적화)
        
        장점:
        1. 노이즈/중복 제거 우선 → 깨끗한 후보군 확보
        2. Coverage 최적화 후순위 → 고품질 패치만으로 대표성 확보
        3. Carpet 같은 Natural Texture 클래스에 유리
        
        Args:
            features: [N x D] feature tensor
            budget: Total budget (B)
            
        Returns:
            Final sampled features [B x D]
        """
        N = len(features)
        
        # NOTE: This method is disabled for Algorithm 1 (use_reverse_hybrid=False)
        # Phase 2 기능 2: Class-conditional τ scheduling (REMOVED for Algorithm 1)
        # - class_tau_multipliers was removed for clean Algorithm 1 implementation
        tau_base = self.tau  # Use input τ directly (no multipliers)
        
        # Stage 1: Adaptive τ-filtering (전체 패치 대상)
        LOGGER.info(f"Reverse Hybrid Stage 1: Adaptive τ-filtering (전체 {N} patches)")
        
        # Normalize features for cosine similarity
        features_norm = F.normalize(features, p=2, dim=1)
        
        # Phase 2 기능 1: Multi-scale density adaptive τ
        # NOTE: Disabled for Reverse Hybrid due to memory constraints
        adaptive_tau = None
        if self.use_multiscale_density:
            LOGGER.warning(
                "Reverse Hybrid: Skipping multi-scale density due to memory constraints. "
                "Using static/class-conditional tau."
            )
            # Skip _compute_multiscale_density to avoid CUDA OOM
            # Calculating N x N density matrix for full training set (N~200k) requires ~160GB
            # adaptive_tau remains None, so filtering will use tau_base
        
        # Phase 2.15: Random shuffle to prevent data bias
        # Without shuffle, early stopping may only sample from first few images
        perm = torch.randperm(N, device=features_norm.device)
        features_norm_shuffled = features_norm[perm]
        if adaptive_tau is not None:
            adaptive_tau_shuffled = adaptive_tau[perm]
        else:
            adaptive_tau_shuffled = None
        
        # Select first patch deterministically: farthest from center
        center = torch.mean(features_norm_shuffled, dim=0, keepdim=True)
        center_norm = F.normalize(center, p=2, dim=1)
        cos_sim_to_center = torch.mm(features_norm_shuffled, center_norm.T).squeeze()
        cos_dist_to_center = 1.0 - cos_sim_to_center
        first_idx = torch.argmax(cos_dist_to_center).item()
        
        selected_indices_shuffled = [first_idx]
        
        # Sequential filtering with τ
        with torch.no_grad():
            with tqdm.tqdm(total=N-1, desc="Reverse Hybrid Stage 1: τ-filtering") as pbar:
                for i in range(N):
                    if i == first_idx:
                        continue
                    
                    # Compute min distance to selected patches
                    current_feature = features_norm_shuffled[i:i+1]
                    selected_features = features_norm_shuffled[selected_indices_shuffled]
                    cos_sim = torch.mm(current_feature, selected_features.T)
                    cos_dist = 1.0 - cos_sim
                    min_distance = torch.min(cos_dist).item()
                    
                    # Apply adaptive τ threshold (Phase 2)
                    tau_threshold = adaptive_tau_shuffled[i].item() if adaptive_tau_shuffled is not None else tau_base
                    if min_distance > tau_threshold:
                        selected_indices_shuffled.append(i)
                    
                    pbar.update(1)
                    if (i + 1) % 1000 == 0:
                        pbar.set_postfix({"selected": len(selected_indices_shuffled)})
        
        # Map shuffled indices back to original indices
        original_indices = perm[selected_indices_shuffled].cpu().numpy()
        stage1_features = features[original_indices]
        
        LOGGER.info(
            f"Stage 1 complete: {len(stage1_features)} patches "
            f"({100*len(stage1_features)/N:.1f}% of original)"
        )
        
        # Stage 2: Approximate Greedy Coreset (정제된 후보군에서 최종 선택)
        if len(stage1_features) <= budget:
            # 이미 budget 이하면 그대로 사용
            LOGGER.info(f"Stage 1 output already within budget. Skipping Stage 2.")
            final_features = stage1_features
        else:
            # Greedy Coreset으로 budget까지 축소
            LOGGER.info(f"Reverse Hybrid Stage 2: Approximate Greedy Coreset ({budget} patches)")
            
            coreset_sampler = ApproximateGreedyCoresetSampler(
                percentage=budget / len(stage1_features),
                device=self.device,
                dimension_to_project_features_to=self.dimension_to_project_features_to,
            )
            
            final_features = coreset_sampler.run(stage1_features)
            
            LOGGER.info(
                f"Stage 2 complete: {len(final_features)} patches "
                f"({100*len(final_features)/len(stage1_features):.1f}% of Stage 1)"
            )
        
        LOGGER.info(f"Reverse Hybrid sampling complete: {len(final_features)} patches")
        
        return final_features

    def _d2_seeding(
        self,
        features: torch.Tensor,
        budget: int,
        class_name: Optional[str] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Stage 2: D^2 seeding for budget management (cosine distance based).

        Hybrid k-means++ style sampling with class-conditional randomness.
        Depending on the class, selection is either fully probabilistic
        (texture classes need high diversity) or deterministic (structural/
        fine-grained classes need stability).

        Selection modes:
          randomness=1.0  → Pure k-means++: P(i) ∝ D^beta(i)  (texture)
          randomness=0.0  → Pure Greedy:     argmax D^beta(i)  (structural)
          0 < r < 1       → Hybrid: probabilistic with probability r

        Class randomness table:
          texture (carpet, grid, tile)              → 1.0 (full probabilistic)
          structural (bottle, cable, zipper)        → 0.5
          fine-grained (screw, capsule, hazelnut)  → 0.1
          default (class_name=None)                → 0.0 (backward compat.)

        Class D^beta exponents are sourced from the CLASS_D2_EXPONENTS table
        defined in __init__.

        Ablation experiment commands:
        -----------------------------------------------------------------------
        # capsule (fine-grained): compare deterministic vs hybrid-0.1
        export PYTHONPATH=src
        # Baseline (deterministic, current):
        python auto_ccifps.py --class_name capsule --dataset_path data \\
            --layers L2-3 --budget 70000 --seed 1 --gpu_id 0 \\
            --results_path results/ablation_d2/capsule_det
        # Hybrid 0.1 (after this patch):
        python auto_ccifps.py --class_name capsule --dataset_path data \\
            --layers L2-3 --budget 70000 --seed 1 --gpu_id 0 \\
            --results_path results/ablation_d2/capsule_hybrid

        # carpet (texture): compare deterministic vs hybrid-1.0
        python auto_ccifps.py --class_name carpet --dataset_path data \\
            --layers L2-3 --budget 70000 --seed 1 --gpu_id 0 \\
            --results_path results/ablation_d2/carpet_det
        python auto_ccifps.py --class_name carpet --dataset_path data \\
            --layers L2-3 --budget 70000 --seed 1 --gpu_id 0 \\
            --results_path results/ablation_d2/carpet_hybrid
        -----------------------------------------------------------------------

        Args:
            features: [N x D] irredundant features
            budget: Target number of patches
            class_name: Optional class name for class-conditional randomness.
                        If None, uses deterministic argmax (backward compat.).

        Returns:
            (selected_indices [budget], weights [budget])
        """
        # ── Class-conditional randomness table ───────────────────────────────
        CLASS_RANDOMNESS = {
            # texture: benefit most from diversity → full probabilistic
            'carpet': 1.0, 'grid': 1.0, 'tile': 1.0,
            # structural: moderate randomness
            'bottle': 0.5, 'cable': 0.5, 'zipper': 0.5,
            # fine-grained: stable determinism preferred
            'screw': 0.1, 'capsule': 0.1, 'hazelnut': 0.1,
        }
        # Class-conditional D^beta exponents (mirrors CLASS_D2_EXPONENTS in __init__)
        CLASS_D2_EXPONENTS = {
            'grid': 1.6, 'carpet': 1.7, 'tile': 1.6,
            'leather': 1.5, 'wood': 1.7, 'zipper': 1.8,
            'transistor': 2.0, 'metal_nut': 2.0, 'pill': 2.0, 'bottle': 2.0,
            'screw': 1.4, 'hazelnut': 1.5, 'cable': 1.6,
            'toothbrush': 1.3, 'capsule': 1.5,
        }

        randomness = CLASS_RANDOMNESS.get(class_name, 0.0) if class_name else 0.0
        beta = CLASS_D2_EXPONENTS.get(class_name, 2.0) if class_name else 2.0

        if class_name:
            LOGGER.info(
                f"[D2-seeding] class={class_name}: randomness={randomness}, beta={beta}"
            )

        N = len(features)
        if budget >= N:
            return np.arange(N), np.ones(N, dtype=np.float32)

        selected_indices = []
        remaining_indices = list(range(N))

        # Normalize features for cosine distance
        features_norm = F.normalize(features, p=2, dim=1)

        # Select first patch deterministically: farthest from center
        center = torch.mean(features_norm, dim=0, keepdim=True)
        center_norm = F.normalize(center, p=2, dim=1)
        cos_dist_to_center = 1.0 - torch.mm(features_norm, center_norm.T).squeeze()
        first_idx = torch.argmax(cos_dist_to_center).item()
        selected_indices.append(first_idx)
        remaining_indices.remove(first_idx)

        with torch.no_grad():
            with tqdm.tqdm(total=budget - 1, desc=f"D^{beta} seeding (r={randomness:.1f})") as pbar:
                for _ in range(budget - 1):
                    if len(remaining_indices) == 0:
                        break

                    remaining_features_norm = features_norm[remaining_indices]   # [R x D]
                    selected_features_norm = features_norm[selected_indices]     # [S x D]

                    cos_sim = torch.mm(remaining_features_norm, selected_features_norm.T)
                    distances = 1.0 - cos_sim  # [R x S]
                    min_distances = torch.min(distances, dim=1).values  # [R]

                    # D^beta weighting
                    d2_weights = torch.clamp(min_distances, min=1e-8) ** beta

                    # Hybrid selection: probabilistic with probability `randomness`
                    if randomness > 0.0 and np.random.rand() < randomness:
                        probs = d2_weights / (d2_weights.sum() + 1e-10)
                        probs_np = probs.cpu().numpy()
                        probs_np = np.clip(probs_np, 0.0, 1.0)
                        probs_np /= probs_np.sum()
                        sampled_idx = int(np.random.choice(len(remaining_indices), p=probs_np))
                    else:
                        sampled_idx = int(torch.argmax(d2_weights).item())

                    selected_patch_idx = remaining_indices[sampled_idx]
                    selected_indices.append(selected_patch_idx)
                    remaining_indices.pop(sampled_idx)
                    pbar.update(1)

        indices = np.array(selected_indices)
        weights = np.ones(len(indices), dtype=np.float32)
        return indices, weights


class RandomSampler(BaseSampler):
    def __init__(self, percentage: float):
        super().__init__(percentage)

    def run(
        self, features: Union[torch.Tensor, np.ndarray]
    ) -> Union[torch.Tensor, np.ndarray]:
        """Randomly samples input feature collection.

        Args:
            features: [N x D]
        """
        num_random_samples = int(len(features) * self.percentage)
        subset_indices = np.random.choice(
            len(features), num_random_samples, replace=False
        )
        subset_indices = np.array(subset_indices)
        return features[subset_indices]
