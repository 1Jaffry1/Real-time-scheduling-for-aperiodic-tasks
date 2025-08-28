### FINAL

import numpy as np
import random
import copy
import csv


CONTEXT_SWITCH_TIME = 1  # in clock cycles
NUM_CORES=1000

# --- Data Structures ---

class Task:
    def __init__(self, id, arrival_time, burst_time, deadline, priority):
        self.id = id
        self.arrival_time = arrival_time
        self.burst_time = burst_time
        self.deadline = deadline
        self.priority = priority
        self.start_time = None
        self.finish_time = None
        self.assigned_core = None
        self.remaining_time = burst_time
        self.wcet = burst_time  # For emergency criterion

class Core:
    def __init__(self, id):
        self.id = id
        self.available_time = 0
        self.total_busy_time = 0

# --- Fuzzy Neural Network ---

def fuzzify(value, bounds):
    low, mid, high = bounds
    if value < low:
        return [1.0, 0.0, 0.0]
    elif value < mid:
        return [(mid - value) / (mid - low), (value - low) / (mid - low), 0.0]
    elif value < high:
        return [0.0, (high - value) / (high - mid), (value - mid) / (high - mid)]
    else:
        return [0.0, 0.0, 1.0]

class FNN:
    def __init__(self, rule_weights):
        self.rule_weights = rule_weights  # 243 weights (3^5 for 5 inputs)

    def evaluate(self, core_util, task_priority, deadline_tightness, core_reliability, core_mtbf):
        util_mf = fuzzify(core_util, (0, 0.5, 1.0))
        prio_mf = fuzzify(task_priority, (1, 2, 3))
        tight_mf = fuzzify(deadline_tightness, (0, 0.5, 1.0))
        rel_mf = fuzzify(core_reliability, (0.95, 0.98, 1.0))
        mtbf_mf = fuzzify(core_mtbf, (0, 10, 100))
        outputs = []
        idx = 0
        for i in range(3):
            for j in range(3):
                for k in range(3):
                    for l in range(3):
                        for m in range(3):
                            firing_strength = util_mf[i] * prio_mf[j] * tight_mf[k] * rel_mf[l] * mtbf_mf[m]
                            outputs.append(firing_strength * self.rule_weights[idx])
                            idx += 1
        total_strength = sum([util_mf[i//81]*prio_mf[(i//27)%3]*tight_mf[(i//9)%3]*rel_mf[(i//3)%3]*mtbf_mf[i%3] for i in range(243)])
        if total_strength == 0:
            return 1e6
        return sum(outputs) / total_strength

# --- Reliability and MTBF ---

def calc_reliability(core):
    util = min(1.0, core.total_busy_time / (core.available_time if core.available_time > 0 else 1))
    k = 0.05
    reliability = np.exp(-k * util)
    return reliability

def calc_failure_rate(core):
    util = min(1.0, core.total_busy_time / (core.available_time if core.available_time > 0 else 1))
    k = 0.05
    return k * util + 1e-6

def calc_mtbf(core):
    return 1.0 / calc_failure_rate(core)

def system_mtbf(cores):
    total_failure_rate = sum(calc_failure_rate(core) for core in cores)
    return 1.0 / total_failure_rate if total_failure_rate > 0 else 0

# --- NSGA-II ---

def fast_non_dominated_sort(population_objs):
    S = [[] for _ in range(len(population_objs))]
    front = [[]]
    n = [0 for _ in range(len(population_objs))]
    rank = [0 for _ in range(len(population_objs))]

    for p in range(len(population_objs)):
        S[p] = []
        n[p] = 0
        for q in range(len(population_objs)):
            if dominates(population_objs[p], population_objs[q]):
                S[p].append(q)
            elif dominates(population_objs[q], population_objs[p]):
                n[p] += 1
        if n[p] == 0:
            rank[p] = 0
            front[0].append(p)
    i = 0
    while front[i]:
        Q = []
        for p in front[i]:
            for q in S[p]:
                n[q] -= 1
                if n[q] == 0:
                    rank[q] = i + 1
                    Q.append(q)
        i += 1
        front.append(Q)
    del front[-1]
    return front

def dominates(obj1, obj2):
    better = False
    for a, b in zip(obj1, obj2):
        if a > b:
            return False
        elif a < b:
            better = True
    return better

def crowding_distance(objs):
    l = len(objs)
    distance = [0.0] * l
    for m in range(len(objs[0])):
        obj_m = [obj[m] for obj in objs]
        sorted_idx = np.argsort(obj_m)
        distance[sorted_idx[0]] = distance[sorted_idx[-1]] = float('inf')
        min_m = obj_m[sorted_idx[0]]
        max_m = obj_m[sorted_idx[-1]]
        if max_m - min_m == 0:
            continue
        for i in range(1, l - 1):
            distance[sorted_idx[i]] += (obj_m[sorted_idx[i + 1]] - obj_m[sorted_idx[i - 1]]) / (max_m - min_m)
    return distance

def nsga2(tasksets, pop_size=20, generations=30, num_cores=NUM_CORES):
    population = [np.random.rand(243) for _ in range(pop_size)]
    for gen in range(generations):
        objs = []
        for ind in population:
            fnn = FNN(ind)

            makespan, avg_rel, sys_mtbf = evaluate_fnn_on_tasksets(tasksets, fnn, num_cores)
            objs.append([makespan, -avg_rel, -sys_mtbf])
        fronts = fast_non_dominated_sort(objs)
        new_population = []
        for front in fronts:
            if len(new_population) + len(front) > pop_size:
                cd = crowding_distance([objs[i] for i in front])
                sorted_front = [x for _, x in sorted(zip(cd, front), key=lambda pair: -pair[0])]
                new_population.extend([population[i] for i in sorted_front[:pop_size - len(new_population)]])
                break
            else:
                new_population.extend([population[i] for i in front])
        while len(new_population) < pop_size:
            parent1, parent2 = random.sample(new_population, 2)
            cross_point = random.randint(1, 242)
            child = np.concatenate([parent1[:cross_point], parent2[cross_point:]])
            if random.random() < 0.2:
                idx = random.randint(0, 242)
                child[idx] = random.random()
            new_population.append(child)
        population = new_population
    best_ind = population[0]
    return FNN(best_ind)

# --- Emergency Criterion and Ready List ---

def sort_ready_list_by_emergency(ready_list, app_deadline):
    # Lower (DApp - WCET) is more urgent
    return sorted(ready_list, key=lambda t: app_deadline - t.burst_time)

# --- Simulation and Evaluation ---

def simulate_schedule(tasks, fnn, num_cores=NUM_CORES, app_deadline=None):
    tasks = copy.deepcopy(tasks)
    completed_ids = set()
    cores = [Core(i) for i in range(num_cores)]
    time = 0
    scheduled = set()
    while len(completed_ids) < len(tasks):
        ready_list = [t for t in tasks if t.id not in scheduled and t.arrival_time <= time]
        if not ready_list:
            next_times = [t.arrival_time for t in tasks if t.id not in scheduled]
            next_core_times = [core.available_time for core in cores if core.available_time > time]
            candidates = next_times + next_core_times
            if not candidates:
                break
            time = min(candidates)
            continue
        if app_deadline is None:
            app_deadline = max(t.deadline for t in tasks)
        sorted_ready = sort_ready_list_by_emergency(ready_list, app_deadline)
        for core in cores:
            if core.available_time <= time and sorted_ready:
                best_task = None
                best_score = float('inf')
                for task in sorted_ready:
                    if task.id in scheduled:
                        continue
                    core_util = min(1.0, core.total_busy_time / (time + 1))
                    prio_norm = task.priority / 3
                    tightness = max(0.0, min(1.0, (task.deadline - (time + task.burst_time)) / max(1, task.deadline)))
                    reliability = calc_reliability(core)
                    mtbf = calc_mtbf(core)
                    score = fnn.evaluate(core_util, prio_norm, tightness, reliability, mtbf)
                    if score < best_score:
                        best_score = score
                        best_task = task
                if best_task:
                    best_task.start_time = time + CONTEXT_SWITCH_TIME
                    best_task.finish_time = best_task.start_time + best_task.burst_time
                    best_task.assigned_core = core.id
                    core.available_time = best_task.finish_time
                    core.total_busy_time += best_task.burst_time
                    scheduled.add(best_task.id)
        # Advance time to next event
        next_times = [core.available_time for core in cores if core.available_time > time]
        next_task_arrivals = [t.arrival_time for t in tasks if t.id not in scheduled and t.arrival_time > time]
        candidates = next_times + next_task_arrivals
        if not candidates:
            break
        time = min(candidates)
        # Mark finished tasks as completed
        for t in tasks:
            if getattr(t, "finish_time", None) == time:
                completed_ids.add(t.id)
    makespan = max(t.finish_time for t in tasks if hasattr(t, "finish_time"))
    avg_reliability = np.mean([calc_reliability(core) for core in cores])
    sys_mtbf = system_mtbf(cores)
    return makespan, avg_reliability, sys_mtbf


def evaluate_fnn_on_tasksets(tasksets, fnn, num_cores=NUM_CORES):
    makespans = []
    reliabilities = []
    mtbfs = []
    for taskset in tasksets:
        makespan, avg_rel, sys_mtbf = simulate_schedule(taskset, fnn, num_cores)
        makespans.append(makespan)
        reliabilities.append(avg_rel)
        mtbfs.append(sys_mtbf)
    return np.mean(makespans), np.mean(reliabilities), np.mean(mtbfs)



def enf_s_simulation(tasksets, fnn, num_cores=NUM_CORES, simulation_time=120):
    grand_total_deadline_misses = 0
    summary_log = []
    missed_priorities_log = []
    taskset_id = -1

    for taskset_ in tasksets:
        taskset_id += 1
        completed_tasks = []
        missed_priorities = []
        deadline_miss_times = []
        busy_time = 0
        taskset_size = len(taskset_)
        cores = [Core(i) for i in range(num_cores)]
        core_tasks = [None] * num_cores
        time = 0
        tasks = copy.deepcopy(taskset_)
        completed_ids = set()
        scheduled = set()
        print(f"\n🔵 ENF-S: Taskset #{taskset_id}\nt  1  |  2\n------|---")
        app_deadline = max(t.deadline for t in tasks)
        while len(completed_ids) < len(tasks):
            ready_list = [t for t in tasks if t.id not in scheduled and t.arrival_time <= time]
            if not ready_list:
                next_times = [t.arrival_time for t in tasks if t.id not in scheduled]
                next_core_times = [core.available_time for core in cores if core.available_time > time]
                candidates = next_times + next_core_times
                if not candidates:
                    break
                time = min(candidates)
                continue
            sorted_ready = sort_ready_list_by_emergency(ready_list, app_deadline)
            for core_id in range(num_cores):
                if (core_tasks[core_id] is None or time >= getattr(core_tasks[core_id], 'finish_time', 0)) and sorted_ready:
                    best_task = None
                    best_score = float('inf')
                    for task in sorted_ready:
                        if task.id in scheduled:
                            continue
                        core_util = 0 if time == 0 else busy_time / (time * num_cores)
                        prio_norm = task.priority / 3
                        tightness = max(0.0, min(1.0, (task.deadline - (time + task.burst_time)) / max(1, task.deadline)))
                        dummy_core = Core(core_id)
                        dummy_core.total_busy_time = busy_time
                        dummy_core.available_time = time
                        reliability = calc_reliability(dummy_core)
                        mtbf = calc_mtbf(dummy_core)
                        score = fnn.evaluate(core_util, prio_norm, tightness, reliability, mtbf)
                        if score < best_score:
                            best_score = score
                            best_task = task
                    if best_task:
                        best_task.start_time = time + CONTEXT_SWITCH_TIME
                        best_task.finish_time = best_task.start_time + best_task.burst_time
                        best_task.assigned_core = core_id
                        core_tasks[core_id] = best_task
                        cores[core_id].available_time = best_task.finish_time
                        cores[core_id].total_busy_time += best_task.burst_time
                        busy_time += best_task.burst_time
                        scheduled.add(best_task.id)
            next_times = [cores[i].available_time for i in range(num_cores) if cores[i].available_time > time]
            next_task_arrivals = [t.arrival_time for t in tasks if t.id not in scheduled and t.arrival_time > time]
            candidates = next_times + next_task_arrivals
            if not candidates:
                break
            time = min(candidates)
            for core_id in range(num_cores):
                task = core_tasks[core_id]
                if task and task.finish_time == time:
                    completed_tasks.append(task)
                    completed_ids.add(task.id)
                    if task.finish_time > task.deadline:
                        missed_priorities.append(getattr(task, 'priority', 'N/A'))
                        deadline_miss_times.append(time)
                    core_tasks[core_id] = None
            core_status = [str(core_tasks[i].id) if core_tasks[i] else "-" for i in range(num_cores)]
            print(f"{time}  {core_status[0]}  |  {core_status[1]}")
        for task in tasks:
            if task.id not in completed_ids:
                missed_priorities.append(getattr(task, 'priority', 'N/A'))
                deadline_miss_times.append(time)
                print(f"⚠️ Task {task.id} did not complete and missed deadline.")
        deadline_misses = len(missed_priorities)
        # Calculate makespan as the maximum finish_time among all completed tasks
        if completed_tasks:
            makespan = max(t.finish_time for t in completed_tasks)
        else:
            makespan = 0
        taskset_utilization = (busy_time / (simulation_time * num_cores)) * 100
        print(f"\n💥 Total Deadline Misses: {deadline_misses}")
        print(f"⏱️ Makespan: {makespan} cycles")
        print(f"⚡ CPU Utilization for this taskset: {taskset_utilization:.2f}%")
        grand_total_deadline_misses += deadline_misses
        summary_log.append([
            taskset_id,
            taskset_size,
            0,
            deadline_misses,
            0,
            f"{taskset_utilization:.2f}",
            makespan
        ])
        missed_priorities_log.append((taskset_id, missed_priorities))

    print("\n🚀 Final Grand Totals for ENF-S:")
    print(f"💥 Grand Total Deadline Misses: {grand_total_deadline_misses}")
    print(f"⚡ Overall CPU Utilization: {taskset_utilization:.2f}%")
    print("\n🧾 Priorities of Missed Deadline Tasks (per Taskset):")
    for tid, plist in missed_priorities_log:
        print(f"Taskset {tid}: Missed Priorities -> {plist}")
    with open('../enfs_taskset_summary.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Taskset_ID',
            'Taskset Size',
            'Preemptions',
            'Deadline_Misses',
            'Data_Transfers',
            'CPU_Utilization(%)',
            'Makespan',
            'Missed_Task_Priorities'])
        for summary, (_, priorities) in zip(summary_log, missed_priorities_log):
            writer.writerow(summary + [','.join(str(p) for p in priorities)])
print("\n✅ Saved ENF-S taskset summaries with missed priorities and makespan to 'enfs_taskset_summary.csv'")


# --- Example Usage ---

if __name__ == "__main__":
    # Each taskset is a list of Task objects, NO predecessors
    from random_taskset import tasks as train
    from aperiodic_task_sets import tasks as test
    tasksets = train
    testsets = test
    print("Training FNN with NSGA-II (this may take a minute)...")
    trained_fnn = nsga2(tasksets, pop_size=10, generations=10)
    print("Training complete.\n")
    enf_s_simulation(testsets, trained_fnn, num_cores=NUM_CORES, simulation_time=120)