"""
Recovery Strategy Agent
Agent 2 of the Construction Schedule Recovery System.
Responsibility:
    Select and prioritize recovery actions from the deterministic
    recovery candidate pool using the analysis produced by Agent 1.
Important:
    This agent proposes recovery strategies.
    It does NOT verify whether the selected strategy actually
    recovers the project.
    Verification is delegated to the recovery
    optimization/scheduling stage.
Pipeline:
    Agent 1 - Schedule Analysis
                |
                v
    Recovery Strategy Agent
                |
                v
       Selected recovery actions
                |
                v
    Recovery Optimization Agent
                |
                v
       Schedule verification
"""
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
# ============================================================
# PATHS
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEDULE_ANALYSIS_DIR = (
    PROJECT_ROOT / "data" / "schedule_analysis"
)
RECOVERY_STRATEGY_DIR = (
    PROJECT_ROOT / "data" / "recovery_strategies"
)
OUTPUT_DIR = (
    PROJECT_ROOT / "data" / "recovery_strategy_agent"
)
# ============================================================
# CONFIGURATION
# ============================================================
AGENT_VERSION = "1.2"
# Number of primary actions recommended
MAX_PRIMARY_ACTIONS = 3
# Number of alternative actions retained
MAX_ALTERNATIVE_ACTIONS = 3
# ------------------------------------------------------------
# Candidate scoring weights
# ------------------------------------------------------------
WEIGHTS = {
    "priority": 0.30,
    "affected_activity": 0.25,
    "direct_activity": 0.15,
    "strategy_match": 0.15,
    "verification_status": 0.10,
    "cost_efficiency": 0.05,
}
# ------------------------------------------------------------
# Action ordering
# ------------------------------------------------------------
ACTION_TYPE_ORDER = {
    "activity_crash": 0,
    "resource_augmentation": 1,
    "resequencing": 2,
    "parallelization": 3,
}
# ============================================================
# JSON HELPERS
# ============================================================
def load_json(path: Path) -> Dict[str, Any]:
    """Load JSON file."""
    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {path}"
        )
    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)
def save_json(
    data: Dict[str, Any],
    path: Path
) -> None:
    """Save JSON file."""
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )
    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )
# ============================================================
# GENERAL HELPERS
# ============================================================
def safe_float(
    value: Any,
    default: float = 0.0
) -> float:
    """Safely convert a value to float."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
def safe_int(
    value: Any,
    default: int = 0
) -> int:
    """Safely convert a value to int."""
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default
def unique_list(
    values: List[Any]
) -> List[Any]:
    """Return unique values while preserving order."""
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
# ============================================================
# INPUT LOADING
# ============================================================
def load_agent_inputs(
    baseline_id: str,
    scenario_id: str
) -> Dict[str, Any]:
    """
    Load Agent 1 analysis and deterministic recovery
    candidate data for one scenario.
    """
    analysis_file = (
        SCHEDULE_ANALYSIS_DIR
        / f"{baseline_id}_analysis.json"
    )
    strategy_file = (
        RECOVERY_STRATEGY_DIR
        / f"{baseline_id}_recovery_strategy.json"
    )
    if not analysis_file.exists():
        raise FileNotFoundError(
            f"Agent 1 analysis not found: "
            f"{analysis_file}"
        )
    if not strategy_file.exists():
        raise FileNotFoundError(
            f"Recovery candidate file not found: "
            f"{strategy_file}"
        )
    analysis_data = load_json(
        analysis_file
    )
    strategy_data = load_json(
        strategy_file
    )
    analysis_record = find_analysis_record(
        analysis_data,
        scenario_id
    )
    strategy_record = find_strategy_record(
        strategy_data,
        scenario_id
    )
    if analysis_record is None:
        raise ValueError(
            f"Scenario {scenario_id} not found "
            f"in Agent 1 analysis for {baseline_id}"
        )
    if strategy_record is None:
        raise ValueError(
            f"Scenario {scenario_id} not found "
            f"in recovery strategies for {baseline_id}"
        )
    return {
        "analysis": analysis_record,
        "strategy": strategy_record,
    }
# ============================================================
# RECORD LOOKUPS
# ============================================================
def find_analysis_record(
    analysis_data: Dict[str, Any],
    scenario_id: str
) -> Optional[Dict[str, Any]]:
    """
    Find scenario record from Agent 1 output.
    Actual Agent 1 structure:
        {
            "scenario_id": "...",
            "analysis": {
                ...
            }
        }
    """
    scenarios = analysis_data.get(
        "scenarios",
        []
    )
    # Compatibility with any older output
    if not scenarios:
        scenarios = analysis_data.get(
            "scenario_analyses",
            []
        )
    for record in scenarios:
        if record.get(
            "scenario_id"
        ) == scenario_id:
            return record
    return None
def find_strategy_record(
    strategy_data: Dict[str, Any],
    scenario_id: str
) -> Optional[Dict[str, Any]]:
    """
    Find scenario record from deterministic
    recovery candidate generation.
    """
    scenarios = strategy_data.get(
        "scenario_strategies",
        []
    )
    # Compatibility fallback
    if not scenarios:
        scenarios = strategy_data.get(
            "scenarios",
            []
        )
    for record in scenarios:
        if record.get(
            "scenario_id"
        ) == scenario_id:
            return record
    return None
# ============================================================
# AGENT 1 ANALYSIS EXTRACTION
# ============================================================
def get_analysis_payload(
    scenario_record: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract the nested Agent 1 analysis object.
    Actual structure:
        scenario_record
            |
            +-- scenario_id
            |
            +-- analysis
                    |
                    +-- disruption
                    +-- project_impact
                    +-- severity
                    +-- activity_impact
                    +-- propagation
                    +-- recovery_opportunities
                    +-- recovery_direction
    """
    analysis = scenario_record.get(
        "analysis"
    )
    if isinstance(
        analysis,
        dict
    ):
        return analysis
    # Compatibility fallback for older flattened data
    return scenario_record
# ============================================================
# PROBLEM SUMMARY
# ============================================================
def get_problem_summary(
    scenario_record: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract project problem information from Agent 1.
    IMPORTANT:
        Agent 1 stores project_impact and severity
        inside the nested 'analysis' object.
    """
    analysis = get_analysis_payload(
        scenario_record
    )
    project_impact = analysis.get(
        "project_impact",
        {}
    )
    severity = analysis.get(
        "severity",
        {}
    )
    feasible = project_impact.get(
        "feasible",
        True
    )
    project_delay = safe_float(
        project_impact.get(
            "project_delay",
            0
        )
    )
    # Recovery is required if:
    #   1. schedule is infeasible
    #   OR
    #   2. project completion is delayed
    recovery_required = (
        not feasible
        or project_delay > 0
    )
    return {
        "severity": severity.get(
            "level",
            "UNKNOWN"
        ),
        "project_delay": project_delay,
        "baseline_finish": project_impact.get(
            "baseline_finish"
        ),
        "disrupted_finish": project_impact.get(
            "disrupted_finish"
        ),
        "feasible": feasible,
        "solver_status": project_impact.get(
            "solver_status"
        ),
        "delay_percentage": safe_float(
            project_impact.get(
                "delay_percentage",
                0
            )
        ),
        "due_date": project_impact.get(
            "due_date"
        ),
        "baseline_due_date_variance": (
            project_impact.get(
                "baseline_due_date_variance"
            )
        ),
        "disrupted_due_date_variance": (
            project_impact.get(
                "disrupted_due_date_variance"
            )
        ),
        "recovery_required": recovery_required,
    }
# ============================================================
# ACTUAL AFFECTED ACTIVITIES
# ============================================================
def get_actual_affected_activities(
    scenario_record: Dict[str, Any]
) -> List[int]:
    """
    Get activities whose schedules actually changed.
    Agent 1 structure:
        "activity_impact": {
            "actually_affected_activities": [
                {
                    "activity_id": 11,
                    "start_shift": 5,
                    "finish_shift": 5
                }
            ]
        }
    """
    analysis = get_analysis_payload(
        scenario_record
    )
    activity_impact = analysis.get(
        "activity_impact",
        {}
    )
    activities = activity_impact.get(
        "actually_affected_activities",
        []
    )
    result = []
    for activity in activities:
        if isinstance(
            activity,
            dict
        ):
            activity_id = activity.get(
                "activity_id"
            )
        else:
            # Compatibility with simple integer lists
            activity_id = activity
        if activity_id is not None:
            result.append(
                safe_int(
                    activity_id
                )
            )
    return unique_list(
        result
    )
# ============================================================
# DIRECTLY AFFECTED ACTIVITIES
# ============================================================
def get_direct_affected_activities(
    scenario_record: Dict[str, Any]
) -> List[int]:
    """
    Get directly affected activities.
    Agent 1 derives this from the disruption information.
    """
    analysis = get_analysis_payload(
        scenario_record
    )
    disruption = analysis.get(
        "disruption",
        {}
    )
    activity_id = disruption.get(
        "activity_id"
    )
    if activity_id is not None:
        return [
            safe_int(
                activity_id
            )
        ]
    return []
# ============================================================
# DIRECTLY AFFECTED RESOURCE
# ============================================================
def get_direct_affected_resource(
    scenario_record: Dict[str, Any]
) -> Optional[int]:
    """Get directly affected resource if present."""
    analysis = get_analysis_payload(
        scenario_record
    )
    disruption = analysis.get(
        "disruption",
        {}
    )
    resource_id = disruption.get(
        "resource_id"
    )
    if resource_id is None:
        return None
    return safe_int(
        resource_id
    )
# ============================================================
# RECOVERY DIRECTION
# ============================================================
def get_recommended_focus(
    scenario_record: Dict[str, Any]
) -> str:
    """Get Agent 1 recommended recovery focus."""
    analysis = get_analysis_payload(
        scenario_record
    )
    recovery_direction = analysis.get(
        "recovery_direction",
        {}
    )
    return recovery_direction.get(
        "recommended_focus",
        "general_recovery"
    )
# ============================================================
# CANDIDATE EXTRACTION
# ============================================================
def get_candidate_actions(
    strategy_record: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Extract deterministic recovery candidates."""
    candidates = strategy_record.get(
        "candidate_actions",
        []
    )
    return [
        candidate
        for candidate in candidates
        if isinstance(
            candidate,
            dict
        )
    ]
# ============================================================
# STRATEGY MATCHING
# ============================================================
def strategy_matches_focus(
    action_type: str,
    recommended_focus: str
) -> bool:
    """
    Determine whether candidate action type matches
    Agent 1's recommended recovery direction.
    """
    focus = str(
        recommended_focus
    ).lower()
    action = str(
        action_type
    ).lower()
    mapping = {
        "activity_crashing": {
            "activity_crash"
        },
        "resource_augmentation": {
            "resource_augmentation"
        },
        "resequencing": {
            "resequencing"
        },
        "parallelization": {
            "parallelization"
        },
        "general_recovery": {
            "activity_crash",
            "resource_augmentation",
            "resequencing",
            "parallelization",
        },
    }
    return action in mapping.get(
        focus,
        mapping[
            "general_recovery"
        ]
    )
# ============================================================
# CANDIDATE COST
# ============================================================
def get_candidate_cost(
    candidate: Dict[str, Any]
) -> float:
    """
    Get approximate maximum candidate cost.
    This is a ranking signal only.
    It is NOT the final recovery cost.
    """
    estimated_cost = candidate.get(
        "estimated_cost",
        {}
    )
    if not isinstance(
        estimated_cost,
        dict
    ):
        estimated_cost = {}
    minimum_cost = safe_float(
        estimated_cost.get(
            "minimum_cost",
            0
        )
    )
    maximum_cost = safe_float(
        estimated_cost.get(
            "maximum_cost",
            0
        )
    )
    if maximum_cost > 0:
        return maximum_cost
    if minimum_cost > 0:
        return minimum_cost
    cost_per_day = safe_float(
        candidate.get(
            "cost_per_day",
            0
        )
    )
    if cost_per_day > 0:
        return cost_per_day
    cost_per_unit_day = safe_float(
        candidate.get(
            "cost_per_unit_day",
            0
        )
    )
    if cost_per_unit_day > 0:
        return cost_per_unit_day
    return 0.0
# ============================================================
# COST EFFICIENCY
# ============================================================
def calculate_cost_efficiency(
    candidate: Dict[str, Any]
) -> float:
    """
    Calculate a simple priority-to-cost ratio.
    This is only a ranking signal.
    It is NOT actual recovery ROI.
    """
    priority = max(
        safe_float(
            candidate.get(
                "priority_score",
                0
            )
        ),
        0.0
    )
    cost = get_candidate_cost(
        candidate
    )
    if cost <= 0:
        # Zero-cost candidates are not automatically
        # preferred; this simply prevents division by zero.
        return 1.0
    return priority / cost
# ============================================================
# CANDIDATE SCORING
# ============================================================
def calculate_candidate_score(
    candidate: Dict[str, Any],
    affected_activities: List[int],
    direct_activities: List[int],
    recommended_focus: str
) -> Dict[str, Any]:
    """
    Calculate evidence-based candidate ranking score.
    The score prioritizes:
        1. Existing candidate priority
        2. Relevance to actually affected activities
        3. Relevance to directly affected activity
        4. Match with Agent 1 recovery direction
        5. Candidate status
        6. Cost efficiency
    The score does NOT guarantee recovery.
    """
    action_type = candidate.get(
        "action_type",
        "unknown"
    )
    priority_score = safe_float(
        candidate.get(
            "priority_score",
            0
        )
    )
    # --------------------------------------------------------
    # Priority normalization
    # --------------------------------------------------------
    priority_component = min(
        priority_score / 500.0,
        1.0
    )
    # --------------------------------------------------------
    # Activity relevance
    # --------------------------------------------------------
    activity_id = candidate.get(
        "activity_id"
    )
    affected_component = 0.0
    direct_component = 0.0
    if activity_id is not None:
        activity_id = safe_int(
            activity_id
        )
        if activity_id in affected_activities:
            affected_component = 1.0
        if activity_id in direct_activities:
            direct_component = 1.0
    # --------------------------------------------------------
    # Strategy match
    # --------------------------------------------------------
    strategy_component = (
        1.0
        if strategy_matches_focus(
            action_type,
            recommended_focus
        )
        else 0.0
    )
    # --------------------------------------------------------
    # Verification status
    # --------------------------------------------------------
    status = candidate.get(
        "status",
        "candidate"
    )
    verification_component = (
        1.0
        if status == "candidate"
        else 0.0
    )
    # --------------------------------------------------------
    # Cost efficiency
    # --------------------------------------------------------
    cost_efficiency = (
        calculate_cost_efficiency(
            candidate
        )
    )
    cost_component = min(
        cost_efficiency * 10000.0,
        1.0
    )
    # --------------------------------------------------------
    # Final score
    # --------------------------------------------------------
    score = (
        WEIGHTS["priority"]
        * priority_component
        + WEIGHTS["affected_activity"]
        * affected_component
        + WEIGHTS["direct_activity"]
        * direct_component
        + WEIGHTS["strategy_match"]
        * strategy_component
        + WEIGHTS["verification_status"]
        * verification_component
        + WEIGHTS["cost_efficiency"]
        * cost_component
    )
    return {
        "score": round(
            score,
            6
        ),
        "components": {
            "priority": round(
                priority_component,
                6
            ),
            "affected_activity": round(
                affected_component,
                6
            ),
            "direct_activity": round(
                direct_component,
                6
            ),
            "strategy_match": round(
                strategy_component,
                6
            ),
            "verification_status": round(
                verification_component,
                6
            ),
            "cost_efficiency": round(
                cost_component,
                6
            ),
        }
    }
# ============================================================
# CANDIDATE RANKING
# ============================================================
def rank_candidates(
    candidates: List[Dict[str, Any]],
    affected_activities: List[int],
    direct_activities: List[int],
    recommended_focus: str
) -> List[Dict[str, Any]]:
    """Rank recovery candidates."""
    ranked = []
    for candidate in candidates:
        score_data = (
            calculate_candidate_score(
                candidate,
                affected_activities,
                direct_activities,
                recommended_focus
            )
        )
        ranked_candidate = dict(
            candidate
        )
        ranked_candidate[
            "_agent_score"
        ] = score_data[
            "score"
        ]
        ranked_candidate[
            "_score_components"
        ] = score_data[
            "components"
        ]
        ranked.append(
            ranked_candidate
        )
    ranked.sort(
        key=lambda item: (
            -safe_float(
                item.get(
                    "_agent_score",
                    0
                )
            ),
            ACTION_TYPE_ORDER.get(
                item.get(
                    "action_type",
                    ""
                ),
                99
            ),
            safe_int(
                item.get(
                    "activity_id",
                    999999
                )
            ),
            safe_int(
                item.get(
                    "resource_id",
                    999999
                )
            ),
        )
    )
    return ranked
# ============================================================
# ACTION SIMPLIFICATION
# ============================================================
def simplify_action(
    candidate: Dict[str, Any],
    rank: int
) -> Dict[str, Any]:
    """
    Convert internal candidate representation
    into Agent 2 output representation.

    Preserve recovery ranges and cost parameters required
    by the downstream optimization agent.
    """

    return {
        "rank": rank,
        "action_id": candidate.get("action_id"),
        "action_type": candidate.get("action_type"),
        "activity_id": candidate.get("activity_id"),
        "resource_id": candidate.get("resource_id"),
        "priority_score": candidate.get("priority_score"),
        "agent_score": candidate.get("_agent_score"),
        "score_components": candidate.get(
            "_score_components",
            {}
        ),
        "status": candidate.get("status"),

        # Activity crash information
        "normal_duration": candidate.get("normal_duration"),
        "minimum_duration": candidate.get("minimum_duration"),
        "maximum_reduction_days": candidate.get(
            "maximum_reduction_days"
        ),
        "cost_per_day": candidate.get("cost_per_day"),

        # Resource augmentation information
        "original_capacity": candidate.get("original_capacity"),
        "maximum_additional_capacity": candidate.get(
            "maximum_additional_capacity"
        ),
        "cost_per_unit_day": candidate.get(
            "cost_per_unit_day"
        ),

        "estimated_cost": candidate.get(
            "estimated_cost",
            {}
        ),
        "candidate_reason": candidate.get(
            "candidate_reason"
        )
    }

# ============================================================
# STRATEGY SELECTION
# ============================================================
def select_strategy(
    scenario_record: Dict[str, Any],
    strategy_record: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Select primary and alternative recovery actions.
    """
    problem = get_problem_summary(
        scenario_record
    )
    # ========================================================
    # CASE 1
    # Feasible + zero delay
    # ========================================================
    if (
        problem["feasible"]
        and problem["project_delay"] <= 0
    ):
        return {
            "strategy_status":
                "no_recovery_required",
            "recommended_strategy":
                "none",
            "reason": (
                "The disrupted schedule is feasible "
                "and does not increase project "
                "completion time."
            ),
            "selected_actions": [],
            "alternative_actions": [],
            "verification_required":
                False,
            "next_agent":
                "none",
        }
    # ========================================================
    # CASE 2
    # Infeasible schedule
    # ========================================================
    if not problem["feasible"]:
        candidates = get_candidate_actions(
            strategy_record
        )
        # ----------------------------------------------------
        # No feasibility-recovery candidates available
        # ----------------------------------------------------
        if not candidates:
            return {
                "strategy_status":
                    "requires_feasibility_recovery",
                "recommended_strategy":
                    "feasibility_recovery",
                "reason": (
                    "The disrupted schedule is infeasible, "
                    "but no feasibility-recovery candidates "
                    "are currently available in the "
                    "deterministic recovery candidate pool."
                ),
                "selected_actions": [],
                "alternative_actions": [],
                "candidate_count": 0,
                "candidate_availability":
                    "none",
                "verification_required": True,
                "next_agent":
                    "recovery_optimization_agent",
            }
        # ----------------------------------------------------
        # Feasibility-recovery candidates are available
        # ----------------------------------------------------
        affected_activities = (
            get_actual_affected_activities(
                scenario_record
            )
        )
        direct_activities = (
            get_direct_affected_activities(
                scenario_record
            )
        )
        recommended_focus = (
            get_recommended_focus(
                scenario_record
            )
        )
        ranked = rank_candidates(
            candidates,
            affected_activities,
            direct_activities,
            recommended_focus
        )
        # ----------------------------------------------------
        # Select primary feasibility actions
        # ----------------------------------------------------
        selected_internal = ranked[
            :MAX_PRIMARY_ACTIONS
        ]
        alternatives_internal = ranked[
            MAX_PRIMARY_ACTIONS:
            MAX_PRIMARY_ACTIONS
            + MAX_ALTERNATIVE_ACTIONS
        ]
        selected_actions = [
            simplify_action(
                candidate,
                index + 1
            )
            for index, candidate
            in enumerate(
                selected_internal
            )
        ]
        alternative_actions = [
            simplify_action(
                candidate,
                MAX_PRIMARY_ACTIONS
                + index
                + 1
            )
            for index, candidate
            in enumerate(
                alternatives_internal
            )
        ]
        # ----------------------------------------------------
        # Determine strategy type
        # ----------------------------------------------------
        strategy_types = unique_list([
            action["action_type"]
            for action in selected_actions
        ])
        if len(strategy_types) == 1:
            recommended_strategy = (
                strategy_types[0]
            )
        else:
            recommended_strategy = (
                "hybrid_feasibility_recovery"
            )
        return {
            "strategy_status":
                "feasibility_recovery_proposed",
            "recommended_strategy":
                recommended_strategy,
            "reason": (
                "The disrupted schedule is infeasible. "
                "Feasibility-recovery actions were selected "
                "from the deterministic candidate pool using "
                "the same evidence-based ranking used for "
                "normal recovery."
            ),
            "selected_actions":
                selected_actions,
            "alternative_actions":
                alternative_actions,
            "candidate_count":
                len(candidates),
            "candidate_availability":
                "available",
            "verification_required":
                True,
            "next_agent":
                "recovery_optimization_agent",
        }
    # ========================================================
    # CASE 3
    # Positive project delay
    # ========================================================
    candidates = get_candidate_actions(
        strategy_record
    )
    if not candidates:
        return {
            "strategy_status":
                "no_candidates_available",
            "recommended_strategy":
                "recovery_optimization_required",
            "reason": (
                "The project has a positive delay, "
                "but no recovery candidates were generated."
            ),
            "selected_actions": [],
            "alternative_actions": [],
            "verification_required":
                True,
            "next_agent":
                "recovery_optimization_agent",
        }
    # --------------------------------------------------------
    # Gather Agent 1 evidence
    # --------------------------------------------------------
    affected_activities = (
        get_actual_affected_activities(
            scenario_record
        )
    )
    direct_activities = (
        get_direct_affected_activities(
            scenario_record
        )
    )
    recommended_focus = (
        get_recommended_focus(
            scenario_record
        )
    )
    # --------------------------------------------------------
    # Rank candidates
    # --------------------------------------------------------
    ranked = rank_candidates(
        candidates,
        affected_activities,
        direct_activities,
        recommended_focus
    )
    # --------------------------------------------------------
    # Select primary actions
    # --------------------------------------------------------
    selected_internal = ranked[
        :MAX_PRIMARY_ACTIONS
    ]
    alternatives_internal = ranked[
        MAX_PRIMARY_ACTIONS:
        MAX_PRIMARY_ACTIONS
        + MAX_ALTERNATIVE_ACTIONS
    ]
    selected_actions = [
        simplify_action(
            candidate,
            index + 1
        )
        for index, candidate
        in enumerate(
            selected_internal
        )
    ]
    alternative_actions = [
        simplify_action(
            candidate,
            MAX_PRIMARY_ACTIONS
            + index
            + 1
        )
        for index, candidate
        in enumerate(
            alternatives_internal
        )
    ]
    # --------------------------------------------------------
    # Determine recommended strategy type
    # --------------------------------------------------------
    strategy_types = unique_list([
        action[
            "action_type"
        ]
        for action
        in selected_actions
    ])
    if len(strategy_types) == 1:
        recommended_strategy = (
            strategy_types[0]
        )
    else:
        recommended_strategy = (
            "hybrid_recovery"
        )
    return {
        "strategy_status":
            "strategy_proposed",
        "recommended_strategy":
            recommended_strategy,
        "reason": (
            "Recovery actions were selected from "
            "the existing deterministic candidate "
            "pool using project impact, affected "
            "activities, direct impact, Agent 1 "
            "recovery focus, candidate priority, "
            "verification status, and estimated "
            "cost efficiency."
        ),
        "selected_actions":
            selected_actions,
        "alternative_actions":
            alternative_actions,
        "verification_required":
            True,
        "next_agent":
            "recovery_optimization_agent",
    }
# ============================================================
# SELECTION RATIONALE
# ============================================================
def build_selection_rationale(
    scenario_record: Dict[str, Any],
    selection: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate deterministic selection rationale."""
    problem = get_problem_summary(
        scenario_record
    )
    affected = (
        get_actual_affected_activities(
            scenario_record
        )
    )
    direct = (
        get_direct_affected_activities(
            scenario_record
        )
    )
    resource = (
        get_direct_affected_resource(
            scenario_record
        )
    )
    focus = (
        get_recommended_focus(
            scenario_record
        )
    )
    return {
        "severity":
            problem["severity"],
        "project_delay":
            problem["project_delay"],
        "directly_affected_activities":
            direct,
        "directly_affected_resource":
            resource,
        "actually_affected_activities":
            affected,
        "recommended_focus_from_agent_1":
            focus,
        "selection_basis": [
            "Project delay severity",
            "Actual schedule-affected activities",
            "Directly affected activity relevance",
            "Recovery focus identified by Agent 1",
            "Candidate priority score",
            "Candidate verification status",
            "Estimated cost efficiency",
        ],
        "important_note": (
            "The selected actions are recovery "
            "proposals. They are not guaranteed "
            "to recover the project until evaluated "
            "by the recovery optimization and "
            "scheduling verification stage."
        ),
    }
# ============================================================
# SINGLE SCENARIO
# ============================================================
def analyze_scenario(
    baseline_id: str,
    scenario_id: str
) -> Dict[str, Any]:
    """Run Agent 2 for one scenario."""
    inputs = load_agent_inputs(
        baseline_id,
        scenario_id
    )
    scenario_record = inputs[
        "analysis"
    ]
    strategy_record = inputs[
        "strategy"
    ]
    problem = get_problem_summary(
        scenario_record
    )
    selection = select_strategy(
        scenario_record,
        strategy_record
    )
    rationale = build_selection_rationale(
        scenario_record,
        selection
    )
    return {
        "agent":
            "recovery_strategy_agent",
        "agent_version":
            AGENT_VERSION,
        "agentic_stage":
            "recovery_strategy_selection",
        "baseline_id":
            baseline_id,
        "scenario_id":
            scenario_id,
        "problem_summary":
            problem,
        "strategy_selection":
            selection,
        "selection_rationale":
            rationale,
        "verification_required":
            selection[
                "verification_required"
            ],
        "next_agent":
            selection[
                "next_agent"
            ],
    }
# ============================================================
# BASELINE PROCESSING
# ============================================================
def process_baseline(
    baseline_id: str
) -> Dict[str, Any]:
    """
    Process all scenarios for one baseline.
    """
    analysis_file = (
        SCHEDULE_ANALYSIS_DIR
        / f"{baseline_id}_analysis.json"
    )
    strategy_file = (
        RECOVERY_STRATEGY_DIR
        / f"{baseline_id}_recovery_strategy.json"
    )
    if not analysis_file.exists():
        raise FileNotFoundError(
            f"Missing Agent 1 file: "
            f"{analysis_file}"
        )
    if not strategy_file.exists():
        raise FileNotFoundError(
            f"Missing recovery strategy file: "
            f"{strategy_file}"
        )
    analysis_data = load_json(
        analysis_file
    )
    strategy_data = load_json(
        strategy_file
    )
    # --------------------------------------------------------
    # Agent 1 scenarios
    # --------------------------------------------------------
    analysis_scenarios = (
        analysis_data.get(
            "scenarios",
            []
        )
    )
    # Compatibility fallback
    if not analysis_scenarios:
        analysis_scenarios = (
            analysis_data.get(
                "scenario_analyses",
                []
            )
        )
    # --------------------------------------------------------
    # Deterministic recovery candidates
    # --------------------------------------------------------
    strategy_scenarios = (
        strategy_data.get(
            "scenario_strategies",
            []
        )
    )
    strategy_lookup = {
        record.get(
            "scenario_id"
        ): record
        for record
        in strategy_scenarios
    }
    results = []
    failed = 0
    # ========================================================
    # PROCESS EACH SCENARIO
    # ========================================================
    for scenario_record in analysis_scenarios:
        scenario_id = scenario_record.get(
            "scenario_id"
        )
        try:
            if scenario_id is None:
                raise ValueError(
                    "Scenario record has no scenario_id."
                )
            strategy_record = (
                strategy_lookup.get(
                    scenario_id
                )
            )
            if strategy_record is None:
                raise ValueError(
                    f"Recovery strategy missing "
                    f"for {scenario_id}"
                )
            problem = get_problem_summary(
                scenario_record
            )
            selection = select_strategy(
                scenario_record,
                strategy_record
            )
            rationale = (
                build_selection_rationale(
                    scenario_record,
                    selection
                )
            )
            results.append({
                "agent":
                    "recovery_strategy_agent",
                "agent_version":
                    AGENT_VERSION,
                "agentic_stage":
                    "recovery_strategy_selection",
                "baseline_id":
                    baseline_id,
                "scenario_id":
                    scenario_id,
                "problem_summary":
                    problem,
                "strategy_selection":
                    selection,
                "selection_rationale":
                    rationale,
                "verification_required":
                    selection[
                        "verification_required"
                    ],
                "next_agent":
                    selection[
                        "next_agent"
                    ],
            })
        except Exception as error:
            failed += 1
            results.append({
                "scenario_id":
                    scenario_id,
                "status":
                    "failed",
                "error":
                    str(error),
            })
    # ========================================================
    # SUMMARY
    # ========================================================
    successful = (
        len(results) - failed
    )
    recovery_required_count = sum(
        1
        for result
        in results
        if result.get(
            "problem_summary",
            {}
        ).get(
            "recovery_required",
            False
        )
    )
    strategy_proposals = sum(
        1
        for result in results
        if result.get(
            "strategy_selection",
            {}
        ).get(
            "strategy_status"
        ) in {
            "strategy_proposed",
            "feasibility_recovery_proposed"
        }
    )

    feasibility_strategy_proposals = sum(
        1
        for result in results
        if result.get(
            "strategy_selection",
            {}
        ).get(
            "strategy_status"
        ) == "feasibility_recovery_proposed"
    )

    no_recovery_required = sum(
        1
        for result
        in results
        if result.get(
            "strategy_selection",
            {}
        ).get(
            "strategy_status"
        ) == "no_recovery_required"
    )
    infeasible_scenarios = sum(
        1
        for result
        in results
        if result.get(
            "problem_summary",
            {}
        ).get(
            "feasible"
        ) is False
    )
    feasibility_recovery_required = sum(
        1
        for result
        in results
        if result.get(
            "strategy_selection",
            {}
        ).get(
            "strategy_status"
        ) == "requires_feasibility_recovery"
    )
    output = {
        "baseline_id":
            baseline_id,
        "agent":
            "recovery_strategy_agent",
        "agent_version":
            AGENT_VERSION,
        "agentic_stage":
            "recovery_strategy_selection",
        "analysis_source":
            "schedule_analysis_agent",
        "candidate_source":
            "deterministic_recovery_strategy",
        "summary": {
            "total_scenarios":
                len(analysis_scenarios),
            "successful":
                successful,
            "failed":
                failed,
            "recovery_required":
                recovery_required_count,
            "strategies_proposed":
                strategy_proposals,
            "feasibility_strategy_proposals":
                feasibility_strategy_proposals,
            "no_recovery_required":
                no_recovery_required,
            "infeasible_scenarios":
                infeasible_scenarios,
            "feasibility_recovery_required":
                feasibility_recovery_required,
        },
        "scenario_strategies":
            results,
    }
    return output
# ============================================================
# BATCH PROCESSING
# ============================================================
def process_all_baselines() -> None:
    """Process all Agent 1 analysis files."""
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )
    analysis_files = sorted(
        SCHEDULE_ANALYSIS_DIR.glob(
            "*_analysis.json"
        )
    )
    print("=" * 60)
    print("RECOVERY STRATEGY AGENT")
    print("=" * 60)
    print(
        f"Agent 1 analysis files found : "
        f"{len(analysis_files)}"
    )
    if not analysis_files:
        print(
            "ERROR: No Agent 1 analysis files found."
        )
        return
    successful = 0
    failed = 0
    total_scenarios = 0
    total_strategy_proposals = 0
    total_feasibility_strategy_proposals = 0
    total_recovery_required = 0
    total_infeasible = 0
    total_no_recovery = 0
    # ========================================================
    # PROCESS EACH BASELINE
    # ========================================================
    for index, analysis_file in enumerate(
        analysis_files,
        start=1
    ):
        baseline_id = (
            analysis_file.stem
            .replace(
                "_analysis",
                ""
            )
        )
        print(
            f"[{index}/{len(analysis_files)}] "
            f"Processing {baseline_id}"
        )
        try:
            output = process_baseline(
                baseline_id
            )
            output_file = (
                OUTPUT_DIR
                / f"{baseline_id}_recovery_strategy.json"
            )
            save_json(
                output,
                output_file
            )
            summary = output[
                "summary"
            ]
            total_scenarios += (
                summary[
                    "total_scenarios"
                ]
            )
            total_strategy_proposals += (
                summary[
                    "strategies_proposed"
                ]
            )
            total_feasibility_strategy_proposals += (
                summary[
                    "feasibility_strategy_proposals"
                ]
            )
            total_recovery_required += (
                summary[
                    "recovery_required"
                ]
            )
            total_infeasible += (
                summary[
                    "infeasible_scenarios"
                ]
            )
            total_no_recovery += (
                summary[
                    "no_recovery_required"
                ]
            )
            if summary[
                "failed"
            ] == 0:
                successful += 1
            else:
                failed += 1
        except Exception as error:
            failed += 1
            print(
                f"  ERROR: {error}"
            )
    # ========================================================
    # FINAL SUMMARY
    # ========================================================
    print()
    print("=" * 60)
    print("RECOVERY STRATEGY AGENT COMPLETE")
    print("=" * 60)
    print(
        f"Baselines found        : "
        f"{len(analysis_files)}"
    )
    print(
        f"Successfully processed : "
        f"{successful}"
    )
    print(
        f"Failed                 : "
        f"{failed}"
    )
    print(
        f"Total scenarios        : "
        f"{total_scenarios}"
    )
    print(
        f"Recovery required      : "
        f"{total_recovery_required}"
    )
    print(
        f"Strategies proposed    : "
        f"{total_strategy_proposals}"
    )
    print(
    f"Feasibility proposals  : "
    f"{total_feasibility_strategy_proposals}"
    )
    print(
        f"No recovery required   : "
        f"{total_no_recovery}"
    )
    print(
        f"Infeasible scenarios   : "
        f"{total_infeasible}"
    )
    print(
        f"Output directory       : "
        f"{OUTPUT_DIR}"
    )
# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    process_all_baselines()
