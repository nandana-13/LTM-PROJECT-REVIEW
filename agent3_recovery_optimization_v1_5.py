"""

Agent 3 - Recovery Optimization Agent

Construction Schedule Recovery System



Responsibilities

----------------

1. Read authoritative baseline, disruption scenario and Agent 2 output.

2. Expand crash/resource recovery actions into feasible variants.

3. Rebuild the disrupted CP-SAT scheduling model.

4. Verify recovery candidates deterministically.

5. Choose the best VERIFIED recovery plan using:



   1. Minimum recovery gap to baseline

   2. Minimum recovery cost

   3. Minimum number of recovery actions

   4. Minimum project finish



6. Keep resequencing/parallelization explicitly unsupported until

   their exact scheduling semantics are implemented.



Important design rule

---------------------

Agent 2 proposes.

Agent 3 verifies.



No action is considered a recovery plan until CP-SAT produces

a feasible schedule satisfying precedence, resource and disruption

constraints.

"""



from __future__ import annotations



import json

from pathlib import Path

from typing import Any, Dict, List, Optional, Tuple



from ortools.sat.python import cp_model





# ============================================================

# PATHS

# ============================================================



PROJECT_ROOT = Path(__file__).resolve().parents[3]



BASELINE_DIR = PROJECT_ROOT / "data" / "baseline"

DISRUPTION_DIR = PROJECT_ROOT / "data" / "disruption_scenarios"

AGENT2_DIR = PROJECT_ROOT / "data" / "recovery_strategy_agent"

OUTPUT_DIR = PROJECT_ROOT / "data" / "recovery_optimization"





# ============================================================

# CONFIGURATION

# ============================================================



AGENT_VERSION = "1.5"



SOLVER_TIME_LIMIT_SECONDS = 30

NUM_SEARCH_WORKERS = 8



MAX_ACTIONS_FROM_AGENT2 = 6

MAX_COMBINATIONS = 2000



UNSUPPORTED_ACTION_TYPES = {

    "resequencing",

    "parallelization",

}



RESOURCE_AUGMENTATION_COST_MODEL = (

    "temporary_capacity_available_for_entire_recovery_horizon"

)





# ============================================================

# JSON HELPERS

# ============================================================



def load_json(path: Path) -> Dict[str, Any]:

    if not path.exists():

        raise FileNotFoundError(f"File not found: {path}")



    with path.open("r", encoding="utf-8") as file:

        data = json.load(file)



    if not isinstance(data, dict):

        raise ValueError(

            f"Expected JSON object in {path}, "

            f"found {type(data).__name__}"

        )



    return data





def save_json(data: Dict[str, Any], path: Path) -> None:

    path.parent.mkdir(parents=True, exist_ok=True)



    with path.open("w", encoding="utf-8") as file:

        json.dump(data, file, indent=2)





def safe_int(value: Any, default: int = 0) -> int:

    try:

        return int(value)

    except (TypeError, ValueError):

        return default





def safe_float(value: Any, default: float = 0.0) -> float:

    try:

        return float(value)

    except (TypeError, ValueError):

        return default





# ============================================================

# AGENT 2 EXTRACTION

# ============================================================



def _extract_scenario_container(

    container: Any,

) -> Dict[str, Dict[str, Any]]:



    result: Dict[str, Dict[str, Any]] = {}



    if isinstance(container, list):



        for item in container:



            if not isinstance(item, dict):

                continue



            scenario_id = item.get("scenario_id")



            if scenario_id is None:



                nested = item.get("scenario")



                if isinstance(nested, dict):

                    scenario_id = nested.get("scenario_id")



            if scenario_id is not None:

                result[str(scenario_id)] = item



        return result



    if isinstance(container, dict):



        # Example:

        # {"S001": {...}, "S002": {...}}



        direct_records = {}



        for key, value in container.items():



            if not isinstance(value, dict):

                continue



            if str(key).startswith("S"):



                copied = dict(value)



                if copied.get("scenario_id") is None:

                    copied["scenario_id"] = str(key)



                direct_records[str(key)] = copied



        if direct_records:

            return direct_records



        # Dictionary itself is one scenario



        scenario_id = container.get("scenario_id")



        if scenario_id is not None:

            return {

                str(scenario_id): container

            }



        # Nested containers



        possible_keys = [

            "scenario_strategies",

            "scenarios",

            "scenario_analyses",

            "scenario_results",

            "results",

        ]



        for key in possible_keys:



            nested = container.get(key)



            extracted = _extract_scenario_container(nested)



            if extracted:

                return extracted



    return {}





def _recursive_find_scenarios(

    obj: Any,

) -> Dict[str, Dict[str, Any]]:



    if isinstance(obj, dict):



        if obj.get("scenario_id") is not None:



            sid = str(obj["scenario_id"])



            return {

                sid: obj

            }



        for key, value in obj.items():



            if key in {

                "summary",

                "optimization_summary",

                "metadata",

            }:

                continue



            extracted = _extract_scenario_container(value)



            if extracted:

                return extracted



            extracted = _recursive_find_scenarios(value)



            if extracted:

                return extracted



    elif isinstance(obj, list):



        extracted = _extract_scenario_container(obj)



        if extracted:

            return extracted



        for item in obj:



            extracted = _recursive_find_scenarios(item)



            if extracted:

                return extracted



    return {}





def normalize_agent2_scenario(

    raw: Dict[str, Any],

) -> Dict[str, Any]:



    if not isinstance(raw, dict):



        return {

            "scenario_id": None,

            "recovery_required": False,

            "feasible": False,

            "project_delay": 0,

            "disrupted_finish": None,

            "baseline_finish": None,

            "strategy_status": None,

            "recommended_strategy": None,

            "selected_actions": [],

            "alternative_actions": [],

            "verification_required": False,

            "raw_agent2_record": raw,

        }



    problem_summary = raw.get(

        "problem_summary",

        {},

    )



    strategy_selection = raw.get(

        "strategy_selection",

        {},

    )



    if not isinstance(problem_summary, dict):

        problem_summary = {}



    if not isinstance(strategy_selection, dict):

        strategy_selection = {}



    recovery_required = problem_summary.get(

        "recovery_required",

        raw.get("recovery_required", False),

    )



    feasible = problem_summary.get(

        "feasible",

        raw.get("feasible", False),

    )



    project_delay = problem_summary.get(

        "project_delay",

        raw.get("project_delay", 0),

    )



    selected_actions = strategy_selection.get(

        "selected_actions",

        raw.get("selected_actions", []),

    )



    alternative_actions = strategy_selection.get(

        "alternative_actions",

        raw.get("alternative_actions", []),

    )



    if not isinstance(selected_actions, list):

        selected_actions = []



    if not isinstance(alternative_actions, list):

        alternative_actions = []



    return {

        "scenario_id": (

            str(raw["scenario_id"])

            if raw.get("scenario_id") is not None

            else None

        ),



        "recovery_required": bool(recovery_required),



        "feasible": bool(feasible),



        "project_delay": safe_int(project_delay),



        "disrupted_finish":

            problem_summary.get("disrupted_finish"),



        "baseline_finish":

            problem_summary.get("baseline_finish"),



        "strategy_status":

            strategy_selection.get(

                "strategy_status",

                raw.get("strategy_status"),

            ),



        "recommended_strategy":

            strategy_selection.get(

                "recommended_strategy",

                raw.get("recommended_strategy"),

            ),



        "selected_actions": [

            item

            for item in selected_actions

            if isinstance(item, dict)

        ],



        "alternative_actions": [

            item

            for item in alternative_actions

            if isinstance(item, dict)

        ],



        "verification_required": bool(

            strategy_selection.get(

                "verification_required",

                raw.get("verification_required", True),

            )

        ),



        "raw_agent2_record": raw,

    }





def extract_agent2_scenarios(

    agent2: Dict[str, Any],

) -> Dict[str, Dict[str, Any]]:



    possible_keys = [

        "scenario_strategies",

        "scenarios",

        "scenario_analyses",

        "scenario_results",

        "results",

    ]



    # Direct containers

    for key in possible_keys:



        container = agent2.get(key)



        extracted = _extract_scenario_container(

            container

        )



        if extracted:



            return {

                sid: normalize_agent2_scenario(record)

                for sid, record in extracted.items()

            }



    # Nested containers

    for value in agent2.values():



        if not isinstance(value, dict):

            continue



        for key in possible_keys:



            container = value.get(key)



            extracted = _extract_scenario_container(

                container

            )



            if extracted:



                return {

                    sid: normalize_agent2_scenario(record)

                    for sid, record in extracted.items()

                }



    # Recursive fallback

    extracted = _recursive_find_scenarios(agent2)



    return {

        sid: normalize_agent2_scenario(record)

        for sid, record in extracted.items()

    }





# ============================================================

# INPUT LOADING

# ============================================================



def load_inputs(

    baseline_id: str,

) -> Dict[str, Any]:



    baseline_file = (

        BASELINE_DIR /

        f"{baseline_id}_baseline.json"

    )



    baseline = load_json(baseline_file)



    if baseline.get("instance") != baseline_id:



        raise ValueError(

            f"Baseline instance mismatch: "

            f"expected {baseline_id}, "

            f"found {baseline.get('instance')}"

        )



    disruption_file = (

        DISRUPTION_DIR /

        f"{baseline_id}.json"

    )



    disruption_data = load_json(

        disruption_file

    )



    scenarios = {}



    for item in disruption_data.get(

        "scenarios",

        [],

    ):



        if not isinstance(item, dict):

            continue



        scenario_id = item.get("scenario_id")



        if scenario_id is not None:

            scenarios[str(scenario_id)] = item



    agent2_file = (

        AGENT2_DIR /

        f"{baseline_id}_recovery_strategy.json"

    )



    agent2 = load_json(agent2_file)



    agent2_scenarios = extract_agent2_scenarios(

        agent2

    )



    print(

        f"[Agent 2] {baseline_id}: "

        f"found {len(agent2_scenarios)} scenario records"

    )



    if not agent2_scenarios:



        raise ValueError(

            "Agent 2 output was loaded successfully, "

            "but no scenario records could be extracted."

        )



    return {

        "baseline": baseline,

        "scenarios": scenarios,

        "agent2": agent2,

        "agent2_scenarios": agent2_scenarios,

    }





# ============================================================

# BASELINE HELPERS

# ============================================================



def get_baseline_activities(

    baseline: Dict[str, Any],

) -> List[Dict[str, Any]]:



    return baseline["schedule"]["activities"]





def get_activity_map(

    baseline: Dict[str, Any],

) -> Dict[int, Dict[str, Any]]:



    return {

        safe_int(activity["id"]): activity

        for activity in get_baseline_activities(

            baseline

        )

    }





def get_resource_count(

    baseline: Dict[str, Any],

) -> int:



    return safe_int(

        baseline["resources"]["count"]

    )





def get_baseline_capacities(

    baseline: Dict[str, Any],

) -> List[int]:



    return [

        safe_int(value)

        for value in baseline["resources"]["capacities"]

    ]





def get_resource_requirements(

    activity: Dict[str, Any],

    resource_count: int,

) -> List[int]:



    requirements = list(

        activity.get(

            "resource_requirements",

            [],

        )

    )



    if len(requirements) < resource_count:



        requirements.extend(

            [0] * (

                resource_count -

                len(requirements)

            )

        )



    return [

        safe_int(value)

        for value in requirements[:resource_count]

    ]





# ============================================================

# DISRUPTION MODEL

# ============================================================



def get_disrupted_durations(

    baseline: Dict[str, Any],

    scenario: Dict[str, Any],

) -> Dict[int, int]:



    durations = {

        safe_int(activity["id"]):

            safe_int(activity["duration"])

        for activity in get_baseline_activities(

            baseline

        )

    }



    disruption_type = scenario.get("type")



    if disruption_type == "activity_duration_delay":



        activity_id = safe_int(

            scenario["activity_id"]

        )



        durations[activity_id] = safe_int(

            scenario["new_duration"]

        )



    elif disruption_type == "activity_suspension":



        activity_id = safe_int(

            scenario["activity_id"]

        )



        durations[activity_id] = (

            safe_int(

                scenario["original_duration"]

            )

            +

            safe_int(

                scenario["suspension_duration"]

            )

        )



    return durations





def get_disrupted_capacities(

    baseline: Dict[str, Any],

    scenario: Dict[str, Any],

) -> List[int]:



    capacities = get_baseline_capacities(

        baseline

    )



    if scenario.get("type") == "resource_capacity_reduction":



        resource_id = safe_int(

            scenario["resource_id"]

        )



        capacities[resource_id] = safe_int(

            scenario["new_capacity"]

        )



    return capacities





def get_earliest_starts(

    baseline: Dict[str, Any],

    scenario: Dict[str, Any],

) -> Dict[int, int]:



    earliest = {

        safe_int(activity["id"]): 0

        for activity in get_baseline_activities(

            baseline

        )

    }



    if scenario.get("type") == "activity_start_delay":



        activity_id = safe_int(

            scenario["activity_id"]

        )



        earliest[activity_id] = safe_int(

            scenario["new_earliest_start"]

        )



    return earliest





# ============================================================

# AGENT 2 ACTIONS

# ============================================================



def get_selected_actions(

    agent2_scenario: Dict[str, Any],

) -> List[Dict[str, Any]]:



    selected = agent2_scenario.get(

        "selected_actions",

        [],

    )



    if not isinstance(selected, list):

        return []



    return [

        item

        for item in selected

        if isinstance(item, dict)

    ][:MAX_ACTIONS_FROM_AGENT2]





def get_alternative_actions(

    agent2_scenario: Dict[str, Any],

) -> List[Dict[str, Any]]:



    alternatives = agent2_scenario.get(

        "alternative_actions",

        [],

    )



    if not isinstance(alternatives, list):

        return []



    return [

        item

        for item in alternatives

        if isinstance(item, dict)

    ][:MAX_ACTIONS_FROM_AGENT2]





def get_candidate_pool(

    agent2_scenario: Dict[str, Any],

) -> List[Dict[str, Any]]:



    combined = (

        get_selected_actions(agent2_scenario)

        +

        get_alternative_actions(agent2_scenario)

    )



    unique = {}



    for action in combined:



        action_id = action.get(

            "action_id"

        )



        if action_id is None:



            action_id = json.dumps(

                action,

                sort_keys=True,

                default=str,

            )



        unique[str(action_id)] = action    
    # Keep both selected and alternative actions available. Agent 2 can
    # place executable actions in alternatives when selected actions are
    # unsupported. Do not discard those executable alternatives.
    max_pool_size = MAX_ACTIONS_FROM_AGENT2 * 2
    return list(unique.values())[:max_pool_size]





# ============================================================

# CRASH EXPANSION

# ============================================================



def expand_crash_action(

    action: Dict[str, Any],

    baseline: Dict[str, Any],

    scenario: Dict[str, Any],

) -> List[Dict[str, Any]]:



    activity_id = safe_int(

        action.get("activity_id")

    )



    maximum_reduction = safe_int(

        action.get("maximum_reduction_days")

    )



    if maximum_reduction <= 0:

        return []



    activity_map = get_activity_map(

        baseline

    )



    if activity_id not in activity_map:

        return []



    baseline_duration = safe_int(

        activity_map[activity_id]["duration"]

    )



    disrupted_durations = get_disrupted_durations(

        baseline,

        scenario,

    )



    disrupted_duration = safe_int(

        disrupted_durations[activity_id]

    )



    # Crash capacity is a recovery capability, not merely a way of
    # removing an already-introduced disruption.
    #
    # The old implementation limited the crash to:
    #     disrupted_duration - baseline_duration
    # which incorrectly produced zero variants for unaffected activities.
    # Recovery is allowed to crash an activity below baseline duration,
    # subject to the candidate's minimum_duration.
    candidate_minimum_duration = action.get("minimum_duration")

    fallback_minimum_duration = max(
        1,
        int(baseline_duration * 0.80)
    )

    if candidate_minimum_duration is None:
        candidate_minimum_duration = fallback_minimum_duration

    minimum_duration = max(
        1,
        safe_int(
            candidate_minimum_duration,
            default=fallback_minimum_duration,
        ),
    )

    minimum_duration = min(
        minimum_duration,
        baseline_duration,
    )

    maximum_allowed_reduction = min(
        maximum_reduction,
        max(
            0,
            disrupted_duration - minimum_duration,
        ),
    )

    cost_per_day = safe_float(
        action.get("cost_per_day")
    )

    variants = []

    for reduction in range(
        1,
        maximum_allowed_reduction + 1,
    ):
        new_duration = disrupted_duration - reduction

        if new_duration < minimum_duration:
            continue

        variants.append(
            {
                "action_id": action.get("action_id"),
                "action_type": "activity_crash",
                "activity_id": activity_id,
                "quantity": reduction,
                "cost": reduction * cost_per_day,
                "new_duration": new_duration,
                "minimum_duration": minimum_duration,
                "maximum_reduction_days": maximum_reduction,
                "cost_basis": "crash-day",
            }
        )

    return variants





# ============================================================

# RESOURCE AUGMENTATION

# ============================================================



def expand_resource_action(

    action: Dict[str, Any],

    baseline: Dict[str, Any],

    scenario: Dict[str, Any],

) -> List[Dict[str, Any]]:



    resource_id = safe_int(

        action.get("resource_id")

    )



    maximum_additional = safe_int(

        action.get(

            "maximum_additional_capacity"

        )

    )



    if maximum_additional <= 0:

        return []



    # A completely unavailable resource cannot

    # be recovered simply by adding capacity.

    if scenario.get("type") == "resource_unavailability":



        unavailable_resource = safe_int(

            scenario.get("resource_id"),

            default=-1,

        )



        if resource_id == unavailable_resource:

            return []



    capacities = get_disrupted_capacities(

        baseline,

        scenario,

    )



    if not (

        0 <= resource_id < len(capacities)

    ):

        return []



    cost_per_unit_day = safe_float(

        action.get("cost_per_unit_day")

    )



    recovery_horizon = max(

        safe_int(

            baseline["schedule"]["project_finish"]

        ),

        safe_int(

            baseline["schedule"]["makespan"]

        ),

    )



    variants = []



    for additional_capacity in range(

        1,

        maximum_additional + 1,

    ):



        cost = (

            additional_capacity

            *

            cost_per_unit_day

            *

            recovery_horizon

        )



        variants.append(

            {

                "action_id":

                    action.get("action_id"),



                "action_type":

                    "resource_augmentation",



                "resource_id":

                    resource_id,



                "quantity":

                    additional_capacity,



                "added_capacity":

                    additional_capacity,



                "new_capacity":

                    capacities[resource_id]

                    +

                    additional_capacity,



                "cost":

                    cost,



                "cost_basis":

                    "resource-unit-day",



                "cost_horizon_days":

                    recovery_horizon,

            }

        )



    return variants





# ============================================================

# GENERIC ACTION EXPANSION

# ============================================================



def expand_action(

    action: Dict[str, Any],

    baseline: Dict[str, Any],

    scenario: Dict[str, Any],

) -> List[Dict[str, Any]]:



    action_type = str(

        action.get(

            "action_type",

            "",

        )

    ).lower()



    if action_type == "activity_crash":



        return expand_crash_action(

            action,

            baseline,

            scenario,

        )



    if action_type == "resource_augmentation":



        return expand_resource_action(

            action,

            baseline,

            scenario,

        )



    return []





# ============================================================

# CP-SAT SCHEDULER

# ============================================================



def build_and_solve_schedule(

    baseline: Dict[str, Any],

    scenario: Dict[str, Any],

    recovery_actions: List[Dict[str, Any]],

) -> Dict[str, Any]:



    activities = get_baseline_activities(

        baseline

    )



    resource_count = get_resource_count(

        baseline

    )



    durations = get_disrupted_durations(

        baseline,

        scenario,

    )



    capacities = get_disrupted_capacities(

        baseline,

        scenario,

    )



    earliest_starts = get_earliest_starts(

        baseline,

        scenario,

    )



    applied_actions = []



    # --------------------------------------------------------

    # Apply recovery actions

    # --------------------------------------------------------



    for action in recovery_actions:



        action_type = action.get(

            "action_type"

        )



        if action_type == "activity_crash":



            activity_id = safe_int(

                action.get("activity_id")

            )



            if activity_id not in durations:



                return {

                    "feasible": False,

                    "solver_status":

                        "INVALID_RECOVERY_ACTION",

                    "error":

                        f"Unknown activity {activity_id}",

                }



            new_duration = safe_int(

                action.get("new_duration")

            )



            if new_duration < 0:



                return {

                    "feasible": False,

                    "solver_status":

                        "INVALID_RECOVERY_ACTION",

                    "error":

                        "Negative duration.",

                }



            activity_map = get_activity_map(

                baseline

            )



            baseline_duration = safe_int(
                activity_map[activity_id]["duration"]
            )

            # A valid recovery crash may improve an activity below its
            # original baseline duration. Validate against the candidate
            # recovery limit instead of the baseline duration.
            fallback_minimum_duration = max(
                1,
                int(baseline_duration * 0.80)
            )

            minimum_duration = action.get(
                "minimum_duration"
            )

            if minimum_duration is None:
                minimum_duration = fallback_minimum_duration
            else:
                minimum_duration = max(
                    1,
                    safe_int(
                        minimum_duration,
                        default=fallback_minimum_duration,
                    ),
                )

            minimum_duration = min(
                minimum_duration,
                baseline_duration,
            )

            if new_duration < minimum_duration:
                return {
                    "feasible": False,
                    "solver_status":
                        "INVALID_RECOVERY_ACTION",
                    "error": (
                        f"Activity {activity_id} "
                        f"would be crashed below its "
                        f"permitted minimum duration "
                        f"({minimum_duration})."
                    ),
                }

            durations[activity_id] = new_duration



            applied_actions.append(action)



        elif action_type == "resource_augmentation":



            resource_id = safe_int(

                action.get("resource_id")

            )



            if not (

                0 <= resource_id < resource_count

            ):



                return {

                    "feasible": False,

                    "solver_status":

                        "INVALID_RECOVERY_ACTION",

                    "error":

                        f"Unknown resource {resource_id}",

                }



            # Completely unavailable resources

            # cannot be augmented.

            if scenario.get("type") == "resource_unavailability":



                unavailable_resource = safe_int(

                    scenario.get(

                        "resource_id"

                    ),

                    default=-1,

                )



                if resource_id == unavailable_resource:



                    return {

                        "feasible": False,

                        "solver_status":

                            "INVALID_RECOVERY_ACTION",

                        "error": (

                            "Cannot augment a resource "

                            "that is completely unavailable."

                        ),

                    }



            capacities[resource_id] += safe_int(

                action.get(

                    "added_capacity"

                )

            )



            applied_actions.append(action)



        else:



            return {

                "feasible": False,

                "solver_status":

                    "UNSUPPORTED_RECOVERY_ACTION",

                "error": (

                    f"Unsupported recovery "

                    f"action type: {action_type}"

                ),

            }



    # --------------------------------------------------------

    # CP-SAT model

    # --------------------------------------------------------



    model = cp_model.CpModel()



    original_makespan = safe_int(

        baseline["schedule"]["makespan"]

    )



    total_duration = sum(

        durations.values()

    )



    horizon = max(

        original_makespan * 5 + 100,

        total_duration + 100,

    )



    starts = {}

    ends = {}

    intervals = {}



    for activity in activities:



        activity_id = safe_int(

            activity["id"]

        )



        duration = safe_int(

            durations[activity_id]

        )



        start = model.NewIntVar(

            0,

            horizon,

            f"start_{activity_id}",

        )



        end = model.NewIntVar(

            0,

            horizon,

            f"end_{activity_id}",

        )



        interval = model.NewIntervalVar(

            start,

            duration,

            end,

            f"interval_{activity_id}",

        )



        starts[activity_id] = start

        ends[activity_id] = end

        intervals[activity_id] = interval



        model.Add(

            start >= earliest_starts.get(

                activity_id,

                0,

            )

        )



    # --------------------------------------------------------

    # Source

    # --------------------------------------------------------



    source_activity = safe_int(

        baseline[

            "schedule"

        ][

            "source_activity"

        ]

    )



    release_date = safe_int(

        baseline[

            "project_info"

        ][

            "release_date"

        ]

    )



    model.Add(

        starts[source_activity]

        ==

        release_date

    )



    # --------------------------------------------------------

    # Precedence

    # --------------------------------------------------------



    predecessors = {

        safe_int(activity["id"]): []

        for activity in activities

    }



    for activity in activities:



        activity_id = safe_int(

            activity["id"]

        )



        for successor_id in activity.get(

            "successors",

            [],

        ):



            successor_id = safe_int(

                successor_id

            )



            if successor_id in predecessors:



                predecessors[

                    successor_id

                ].append(

                    activity_id

                )



    for activity_id, predecessor_ids in predecessors.items():



        for predecessor_id in predecessor_ids:



            model.Add(

                starts[activity_id]

                >=

                ends[predecessor_id]

            )



    # --------------------------------------------------------

    # Resource constraints

    # --------------------------------------------------------



    for resource_id in range(

        resource_count

    ):



        resource_intervals = []

        resource_demands = []



        for activity in activities:



            activity_id = safe_int(

                activity["id"]

            )



            requirements = get_resource_requirements(

                activity,

                resource_count,

            )



            demand = requirements[

                resource_id

            ]



            if demand > 0:



                resource_intervals.append(

                    intervals[activity_id]

                )



                resource_demands.append(

                    demand

                )



        if resource_intervals:



            model.AddCumulative(

                resource_intervals,

                resource_demands,

                capacities[resource_id],

            )



    # --------------------------------------------------------

    # Resource unavailability

    # --------------------------------------------------------



    if scenario.get("type") == "resource_unavailability":



        affected_activity_id = safe_int(

            scenario[

                "affected_activity_id"

            ]

        )



        unavailable_start = safe_int(

            scenario[

                "unavailable_start"

            ]

        )



        unavailable_end = safe_int(

            scenario[

                "unavailable_end"

            ]

        )



        if affected_activity_id not in starts:



            return {

                "feasible": False,

                "solver_status":

                    "INVALID_SCENARIO",

                "error": (

                    "Affected activity for "

                    "resource unavailability "

                    "does not exist."

                ),

            }



        before = model.NewBoolVar(

            "before_unavailability"

        )



        after = model.NewBoolVar(

            "after_unavailability"

        )



        model.Add(

            ends[affected_activity_id]

            <=

            unavailable_start

        ).OnlyEnforceIf(before)



        model.Add(

            starts[affected_activity_id]

            >=

            unavailable_end

        ).OnlyEnforceIf(after)



        model.AddBoolOr(

            [before, after]

        )



    # --------------------------------------------------------

    # Scheduler objective

    # --------------------------------------------------------



    sink_activity = safe_int(

        baseline[

            "schedule"

        ][

            "sink_activity"

        ]

    )



    model.Minimize(

        starts[sink_activity]

    )



    # --------------------------------------------------------

    # Solve

    # --------------------------------------------------------



    solver = cp_model.CpSolver()



    solver.parameters.max_time_in_seconds = (

        SOLVER_TIME_LIMIT_SECONDS

    )



    solver.parameters.num_search_workers = (

        NUM_SEARCH_WORKERS

    )



    status = solver.Solve(model)



    status_name = solver.StatusName(

        status

    )



    if status not in (

        cp_model.OPTIMAL,

        cp_model.FEASIBLE,

    ):



        return {

            "feasible": False,

            "solver_status": status_name,

            "schedule": None,

            "applied_actions":

                applied_actions,

        }



    # --------------------------------------------------------

    # Build schedule

    # --------------------------------------------------------



    output_activities = []



    for activity in activities:



        activity_id = safe_int(

            activity["id"]

        )



        start_value = solver.Value(

            starts[activity_id]

        )



        finish_value = solver.Value(

            ends[activity_id]

        )



        output_activities.append(

            {

                "id":

                    activity_id,



                "duration":

                    durations[activity_id],



                "start":

                    start_value,



                "finish":

                    finish_value,



                "successors":

                    activity.get(

                        "successors",

                        [],

                    ),



                "resource_requirements":

                    activity.get(

                        "resource_requirements",

                        [],

                    ),

            }

        )



    project_start = min(

        item["start"]

        for item in output_activities

    )



    project_finish = max(

        item["finish"]

        for item in output_activities

    )



    baseline_finish = safe_int(

        baseline[

            "schedule"

        ][

            "project_finish"

        ]

    )



    project_delay = (

        project_finish -

        baseline_finish

    )



    return {

        "feasible": True,



        "solver_status":

            status_name,



        "schedule": {

            "project_start":

                project_start,



            "project_finish":

                project_finish,



            "makespan":

                project_finish -

                project_start,



            "baseline_project_finish":

                baseline_finish,



            "project_delay":

                project_delay,



            "source_activity":

                source_activity,



            "sink_activity":

                sink_activity,



            "solver_status":

                status_name,



            "activities":

                output_activities,



            "resource_capacities":

                capacities,

        },



        "applied_actions":

            applied_actions,

    }





# ============================================================

# COST

# ============================================================



def total_recovery_cost(

    recovery_actions: List[Dict[str, Any]],

) -> float:



    return sum(

        safe_float(

            action.get("cost")

        )

        for action in recovery_actions

    )





# ============================================================

# RECOVERY OBJECTIVE

# ============================================================



def recovery_objective_key(

    result: Dict[str, Any],

    baseline_finish: int,

) -> Tuple[int, float, int, int]:



    schedule = result["schedule"]



    project_finish = safe_int(

        schedule["project_finish"]

    )



    # 0 means the baseline finish has been

    # recovered or better.

    recovery_gap = max(

        0,

        project_finish -

        baseline_finish,

    )



    recovery_cost = total_recovery_cost(

        result["applied_actions"]

    )



    action_count = len(

        result["applied_actions"]

    )



    return (

        recovery_gap,

        recovery_cost,

        action_count,

        project_finish,

    )





# ============================================================

# ACTION VARIANTS

# ============================================================



def build_action_variants(

    baseline: Dict[str, Any],

    scenario: Dict[str, Any],

    candidate_pool: List[Dict[str, Any]],

) -> Tuple[

    List[Dict[str, Any]],

    List[str],

]:



    variants = []

    unsupported = []



    for candidate in candidate_pool:



        action_type = str(

            candidate.get(

                "action_type",

                "",

            )

        ).lower()



        if action_type in UNSUPPORTED_ACTION_TYPES:



            unsupported.append(

                str(

                    candidate.get(

                        "action_id"

                    )

                )

            )



            continue



        variants.extend(

            expand_action(

                candidate,

                baseline,

                scenario,

            )

        )



    return variants, unsupported





# ============================================================

# COMBINATION GENERATION

# ============================================================



def generate_combinations(

    variants: List[Dict[str, Any]],

) -> List[List[Dict[str, Any]]]:



    by_action_id = {}



    for variant in variants:



        action_id = str(

            variant.get(

                "action_id"

            )

        )



        by_action_id.setdefault(

            action_id,

            [],

        ).append(variant)



    action_ids = sorted(

        by_action_id

    )



    # Empty combination is retained only as

    # the disrupted schedule reference.

    combinations = [[]]



    for action_id in action_ids:



        new_combinations = list(

            combinations

        )



        for current in combinations:



            for variant in by_action_id[

                action_id

            ]:



                new_combinations.append(

                    current + [variant]

                )



                if len(

                    new_combinations

                ) >= MAX_COMBINATIONS:



                    return new_combinations[

                        :MAX_COMBINATIONS

                    ]



        combinations = new_combinations



    return combinations





# ============================================================

# RESULT BUILDER

# ============================================================



def build_base_result(

    baseline: Dict[str, Any],

    scenario: Dict[str, Any],

    agent2_scenario: Dict[str, Any],

    status: str,

    verified: bool,

    verification_performed: bool,

) -> Dict[str, Any]:



    return {

        "baseline_id":

            baseline["instance"],



        "scenario_id":

            str(

                scenario["scenario_id"]

            ),



        "disruption_type":

            scenario.get("type"),



        "agent":

            "recovery_optimization_agent",



        "agent_version":

            AGENT_VERSION,



        "optimization_status":

            status,



        "verified":

            verified,



        "verification_performed":

            verification_performed,



        "recovery_required":

            bool(

                agent2_scenario.get(

                    "recovery_required",

                    False,

                )

            ),



        "agent2_strategy_status":

            agent2_scenario.get(

                "strategy_status"

            ),



        "agent2_recommended_strategy":

            agent2_scenario.get(

                "recommended_strategy"

            ),



        "cost_model":

            RESOURCE_AUGMENTATION_COST_MODEL,

    }





# ============================================================

# OPTIMIZE ONE SCENARIO

# ============================================================



def optimize_scenario(

    baseline: Dict[str, Any],

    scenario: Dict[str, Any],

    agent2_scenario: Dict[str, Any],

) -> Dict[str, Any]:



    scenario_id = str(

        scenario["scenario_id"]

    )



    baseline_finish = safe_int(

        baseline[

            "schedule"

        ][

            "project_finish"

        ]

    )



    candidate_pool = get_candidate_pool(

        agent2_scenario

    )



    recovery_required = bool(

        agent2_scenario.get(

            "recovery_required",

            False,

        )

    )



    # ========================================================

    # NO RECOVERY REQUIRED

    # ========================================================



    if not recovery_required:



        result = build_base_result(

            baseline,

            scenario,

            agent2_scenario,

            "no_recovery_required",

            False,

            False,

        )



        result.update(

            {

                "selected_candidate_count":

                    len(candidate_pool),



                "tested_plan_count":

                    0,



                "verified_plan_count":

                    0,



                "best_plan":

                    None,



                "unsupported_actions":

                    [],



                "verification_basis":

                    "agent2_no_recovery_required",



                "note":

                    "Agent 2 marked this scenario as "

                    "requiring no recovery. Agent 3 therefore "

                    "did not perform recovery optimization or "

                    "independent scheduler verification.",

            }

        )



        return result



    # ========================================================

    # BUILD EXECUTABLE ACTION VARIANTS

    # ========================================================



    variants, unsupported = (

        build_action_variants(

            baseline,

            scenario,

            candidate_pool,

        )

    )



    # ========================================================

    # NO EXECUTABLE CANDIDATES

    # ========================================================



    if not variants:



        result = build_base_result(

            baseline,

            scenario,

            agent2_scenario,

            "no_supported_recovery_candidates",

            False,

            True,

        )



        result.update(

            {

                "selected_candidate_count":

                    len(candidate_pool),



                "tested_plan_count":

                    0,



                "verified_plan_count":

                    0,



                "best_plan":

                    None,



                "unsupported_actions":

                    unsupported,



                "note": (

                    "No currently executable recovery "

                    "candidate was supplied. Resequencing "

                    "and parallelization still require "

                    "explicit scheduling semantics."

                ),

            }

        )



        return result



    # ========================================================

    # GENERATE PLANS

    # ========================================================



    combinations = generate_combinations(

        variants

    )



    tested_plan_count = 0

    verified_plan_count = 0



    # Actual disrupted schedule.

    # This is NOT a recovery plan.

    disrupted_reference = None



    # Best actual recovery action plan.

    best_recovery_result = None

    best_recovery_key = None



    # ========================================================

    # VERIFY EACH PLAN

    # ========================================================



    for plan in combinations:



        tested_plan_count += 1



        result = build_and_solve_schedule(

            baseline,

            scenario,

            plan,

        )



        if not result.get(

            "feasible",

            False,

        ):

            continue



        verified_plan_count += 1



        # ----------------------------------------------------

        # Empty plan = disrupted reference only

        # ----------------------------------------------------



        if len(plan) == 0:



            disrupted_reference = result



            continue



        # ----------------------------------------------------

        # Actual recovery plan

        # ----------------------------------------------------



        project_finish = safe_int(

            result[

                "schedule"

            ][

                "project_finish"

            ]

        )



        # If the plan does not improve the disrupted

        # schedule, it is not considered recovery.

        #

        # For an infeasible disrupted scenario, there is

        # no reference schedule, so any feasible recovery

        # action plan is allowed.



        if disrupted_reference is not None:



            disrupted_finish = safe_int(

                disrupted_reference[

                    "schedule"

                ][

                    "project_finish"

                ]

            )



            if project_finish >= disrupted_finish:

                continue



        key = recovery_objective_key(

            result,

            baseline_finish,

        )



        if (

            best_recovery_key is None

            or key < best_recovery_key

        ):



            best_recovery_key = key

            best_recovery_result = result



    # ========================================================

    # NO VERIFIED RECOVERY PLAN

    # ========================================================



    if best_recovery_result is None:



        result = build_base_result(

            baseline,

            scenario,

            agent2_scenario,

            "no_verified_recovery_plan",

            False,

            True,

        )



        result.update(

            {

                "selected_candidate_count":

                    len(candidate_pool),



                "tested_plan_count":

                    tested_plan_count,



                "verified_plan_count":

                    verified_plan_count,



                "best_plan":

                    None,



                "unsupported_actions":

                    unsupported,



                "objective": {

                    "priority": [

                        "minimum_recovery_gap",

                        "minimum_recovery_cost",

                        "minimum_action_count",

                        "minimum_project_finish",

                    ],



                    "baseline_project_finish":

                        baseline_finish,

                },



                "note": (

                    "All executable candidate combinations "

                    "were tested by CP-SAT, but no recovery "

                    "action plan produced a verified "

                    "improvement over the disrupted schedule."

                ),

            }

        )



        return result



    # ========================================================

    # BEST VERIFIED RECOVERY PLAN

    # ========================================================



    best_schedule = best_recovery_result[

        "schedule"

    ]



    applied_actions = best_recovery_result[

        "applied_actions"

    ]



    recovery_cost = total_recovery_cost(

        applied_actions

    )



    project_finish = safe_int(

        best_schedule[

            "project_finish"

        ]

    )



    project_delay = (

        project_finish -

        baseline_finish

    )



    recovered_to_baseline = (

        project_finish <=

        baseline_finish

    )



    # --------------------------------------------------------

    # Status

    # --------------------------------------------------------



    if recovered_to_baseline:



        optimization_status = (

            "verified_recovery_to_baseline"

        )



    else:



        optimization_status = (

            "verified_partial_recovery"

        )



    result = build_base_result(

        baseline,

        scenario,

        agent2_scenario,

        optimization_status,

        True,

        True,

    )



    result.update(

        {

            "selected_candidate_count":

                len(candidate_pool),



            "tested_plan_count":

                tested_plan_count,



            "verified_plan_count":

                verified_plan_count,



            "unsupported_actions":

                unsupported,



            "objective": {

                "priority": [

                    "minimum_recovery_gap",

                    "minimum_recovery_cost",

                    "minimum_action_count",

                    "minimum_project_finish",

                ],



                "baseline_project_finish":

                    baseline_finish,



                "recovery_gap":

                    max(

                        0,

                        project_finish -

                        baseline_finish,

                    ),

            },



            "best_plan": {

                "recovered_to_baseline":

                    recovered_to_baseline,



                "project_finish":

                    project_finish,



                "project_delay":

                    project_delay,



                "recovery_cost":

                    recovery_cost,



                "action_count":

                    len(applied_actions),



                "actions":

                    applied_actions,



                "schedule":

                    best_schedule,

            },



            "cost_model": {

                "resource_augmentation":

                    RESOURCE_AUGMENTATION_COST_MODEL,



                "note": (

                    "Agent 2 provides "

                    "resource-unit-day cost "

                    "but no augmentation time "

                    "window. Agent 3 therefore "

                    "makes additional capacity "

                    "available throughout the "

                    "recovery scheduling horizon."

                ),

            },

        }

    )



    return result



# ============================================================

# PROCESS ONE BASELINE

# ============================================================



def process_one_baseline(

    baseline_id: str,

) -> Dict[str, Any]:



    inputs = load_inputs(

        baseline_id

    )



    baseline = inputs["baseline"]



    scenarios = inputs["scenarios"]



    agent2_scenarios = inputs[

        "agent2_scenarios"

    ]



    results = []



    scenario_ids = sorted(

        scenarios,

        key=lambda value:

            safe_int(

                str(value).replace(

                    "S",

                    "",

                )

            ),

    )



    print()

    print(

        f"Processing baseline {baseline_id}"

    )



    print(

        f"Disruption scenarios : "

        f"{len(scenarios)}"

    )



    print(

        f"Agent 2 scenarios    : "

        f"{len(agent2_scenarios)}"

    )



    missing_agent2 = [

        scenario_id

        for scenario_id in scenario_ids

        if scenario_id not in agent2_scenarios

    ]



    if missing_agent2:



        raise ValueError(

            f"Agent 2 is missing "

            f"{len(missing_agent2)} scenario records "

            f"for {baseline_id}. "

            f"Missing: {missing_agent2}"

        )



    for scenario_id in scenario_ids:



        scenario = scenarios[

            scenario_id

        ]



        agent2_scenario = agent2_scenarios[

            scenario_id

        ]



        print(

            f"  {scenario_id}: "

            f"{scenario.get('type')} | "

            f"recovery_required="

            f"{agent2_scenario.get('recovery_required')} | "

            f"strategy="

            f"{agent2_scenario.get('recommended_strategy')}"

        )



        try:



            result = optimize_scenario(

                baseline,

                scenario,

                agent2_scenario,

            )



            results.append(result)



            print(

                f"      status="

                f"{result.get('optimization_status')} "

                f"verified="

                f"{result.get('verified')}"

            )



        except Exception as error:



            results.append(

                {

                    "baseline_id":

                        baseline_id,



                    "scenario_id":

                        scenario_id,



                    "agent":

                        "recovery_optimization_agent",



                    "agent_version":

                        AGENT_VERSION,



                    "optimization_status":

                        "ERROR",



                    "verified":

                        False,



                    "verification_performed":

                        True,



                    "recovery_required":

                        bool(

                            agent2_scenario.get(

                                "recovery_required",

                                False,

                            )

                        ),



                    "error":

                        str(error),

                }

            )



            print(

                f"      ERROR: {error}"

            )



    # ========================================================

    # SUMMARY

    # ========================================================



    # ONLY genuine CP-SAT verified recovery plans

    # are included here.

    verified = [

        item

        for item in results

        if item.get("verified") is True

        and item.get("verification_performed") is True

    ]



    # Agent 2 said that no recovery was necessary.

    # These are neither verified recovery plans nor failures.

    no_recovery_required = [

        item

        for item in results

        if item.get("optimization_status")

        == "no_recovery_required"

    ]



    recovered_to_baseline = [

        item

        for item in verified

        if (

            item.get("best_plan") or {}

        ).get(

            "recovered_to_baseline",

            False,

        )

    ]



    partial = [

        item

        for item in verified

        if item.get(

            "optimization_status"

        )

        == "verified_partial_recovery"

    ]



    # A failure means recovery was required but

    # no verified recovery plan was obtained.

    failed = [

        item

        for item in results

        if item.get("verified") is False

        and item.get("recovery_required") is True

    ]



    recovery_required_count = sum(

        1

        for item in results

        if item.get(

            "recovery_required"

        ) is True

    )



    return {

        "baseline_id":

            baseline_id,



        "agent":

            "recovery_optimization_agent",



        "agent_version":

            AGENT_VERSION,



        "optimization_summary": {



            "total_scenarios":

                len(results),



            "recovery_required_scenarios":

                recovery_required_count,



            "verified_scenarios":

                len(verified),



            "recovered_to_baseline":

                len(recovered_to_baseline),



            "verified_partial_recovery":

                len(partial),



            "no_recovery_required":

                len(no_recovery_required),



            "failed_or_unverified":

                len(failed),

        },



        "results":

            results,

    }





# ============================================================

# PROCESS ALL BASELINES

# ============================================================



def process_all_baselines() -> None:



    OUTPUT_DIR.mkdir(

        parents=True,

        exist_ok=True,

    )



    baseline_files = sorted(

        BASELINE_DIR.glob(

            "*_baseline.json"

        )

    )



    if not baseline_files:



        print(

            "No baseline files found in:"

        )



        print(

            BASELINE_DIR

        )



        return



    print()

    print("=" * 70)

    print(

        "RECOVERY OPTIMIZATION AGENT"

    )

    print("=" * 70)



    print(

        f"Baselines found : "

        f"{len(baseline_files)}"

    )



    print(

        f"Output directory: "

        f"{OUTPUT_DIR}"

    )



    print()



    successful = 0

    failed_baselines = 0



    total_scenarios = 0

    total_verified = 0

    total_recovered = 0

    total_partial = 0

    total_no_recovery = 0

    total_failed_or_unverified = 0



    for index, baseline_file in enumerate(

        baseline_files,

        start=1,

    ):



        baseline_id = baseline_file.name.replace(

            "_baseline.json",

            "",

        )



        try:



            output = process_one_baseline(

                baseline_id

            )



            output_file = (

                OUTPUT_DIR /

                f"{baseline_id}_recovery_optimization.json"

            )



            save_json(

                output,

                output_file,

            )



            summary = output[

                "optimization_summary"

            ]



            total_scenarios += summary[

                "total_scenarios"

            ]



            total_verified += summary[

                "verified_scenarios"

            ]



            total_recovered += summary[

                "recovered_to_baseline"

            ]



            total_partial += summary[

                "verified_partial_recovery"

            ]



            total_no_recovery += summary[

                "no_recovery_required"

            ]



            total_failed_or_unverified += summary[

                "failed_or_unverified"

            ]



            successful += 1



            print(

                f"[{index:03d}/"

                f"{len(baseline_files):03d}] "

                f"{baseline_id} | "

                f"scenarios="

                f"{summary['total_scenarios']} | "

                f"verified="

                f"{summary['verified_scenarios']} | "

                f"baseline_recovered="

                f"{summary['recovered_to_baseline']} | "

                f"no_recovery="

                f"{summary['no_recovery_required']} | "

                f"failed="

                f"{summary['failed_or_unverified']}"

            )



        except Exception as error:



            failed_baselines += 1



            print(

                f"[{index:03d}/"

                f"{len(baseline_files):03d}] "

                f"{baseline_id} -> "

                f"ERROR: {error}"

            )



    print()

    print("=" * 70)

    print(

        "RECOVERY OPTIMIZATION COMPLETE"

    )

    print("=" * 70)



    print(

        f"Baselines processed  : "

        f"{successful}"

    )



    print(

        f"Baselines failed     : "

        f"{failed_baselines}"

    )



    print(

        f"Scenarios processed  : "

        f"{total_scenarios}"

    )



    print(

        f"Verified recoveries  : "

        f"{total_verified}"

    )



    print(

        f"Recovered to baseline: "

        f"{total_recovered}"

    )



    print(

        f"Partial recoveries   : "

        f"{total_partial}"

    )



    print(

        f"No recovery required : "

        f"{total_no_recovery}"

    )



    print(

        f"Failed/unverified    : "

        f"{total_failed_or_unverified}"

    )



    print(

        f"Output directory     : "

        f"{OUTPUT_DIR}"

    )



    print("=" * 70)





# ============================================================

# TEST ONE BASELINE

# ============================================================



def process_test_baseline() -> None:



    baseline_id = "j301_1"



    print()

    print("=" * 70)



    print(

        "RECOVERY OPTIMIZATION AGENT - TEST MODE"

    )



    print("=" * 70)



    print(

        f"Testing baseline: {baseline_id}"

    )



    print(

        "Only this baseline will be processed."

    )



    print("=" * 70)



    try:



        output = process_one_baseline(

            baseline_id

        )



        output_file = (

            OUTPUT_DIR /

            f"{baseline_id}_recovery_optimization.json"

        )



        save_json(

            output,

            output_file,

        )



        summary = output[

            "optimization_summary"

        ]



        print()

        print("=" * 70)



        print(

            "TEST COMPLETE"

        )



        print("=" * 70)



        print(

            f"Baseline             : "

            f"{baseline_id}"

        )



        print(

            f"Scenarios            : "

            f"{summary['total_scenarios']}"

        )



        print(

            f"Recovery required    : "

            f"{summary['recovery_required_scenarios']}"

        )



        print(

            f"Verified recoveries  : "

            f"{summary['verified_scenarios']}"

        )



        print(

            f"Recovered baseline   : "

            f"{summary['recovered_to_baseline']}"

        )



        print(

            f"Partial recovery     : "

            f"{summary['verified_partial_recovery']}"

        )



        print(

            f"No recovery required : "

            f"{summary['no_recovery_required']}"

        )



        print(

            f"Failed/unverified    : "

            f"{summary['failed_or_unverified']}"

        )



        print(

            f"Output               : "

            f"{output_file}"

        )



        print("=" * 70)



    except Exception as error:



        print()

        print("=" * 70)



        print(

            "TEST FAILED"

        )



        print("=" * 70)



        print(

            f"Error: {error}"

        )



        print("=" * 70)





# ============================================================

# MAIN

# ============================================================



if __name__ == "__main__":



    # --------------------------------------------------------

    # TEST ONLY j301_1 FIRST

    # --------------------------------------------------------

    #

    # After j301_1 is confirmed correct, change this to:

    #

    #     process_all_baselines()

    #

    # --------------------------------------------------------



    process_all_baselines()