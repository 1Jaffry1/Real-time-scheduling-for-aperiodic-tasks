# taskset.py

epsilon = 1e-9

# Global constants (can be overridden externally)
SIMULATION_TIME = 50
ALPHA = 4
BETA = 0
current_time = 0
prange = 1


class Task:
    def __init__(self, id, arrival_time, burst_time, deadline, priority):
        self.relaxation = None
        self.id = id
        self.arrival_time = arrival_time
        self.burst_time = burst_time
        self.deadline = deadline
        self.priority = priority
        self.remaining_time = burst_time
        self.laxity = deadline - burst_time
        self.dropped = False
        self.completion_time = None

    def update_laxity(self, now=None):
        now = now if now is not None else current_time
        self.laxity = self.deadline - self.remaining_time - now
        return self.laxity

    def normalized_laxity(self, active_tasks, now=None):
        now = now if now is not None else current_time
        laxities = [t.update_laxity(now) for t in active_tasks]
        try:
            min_lax = max(min(laxities), 0)
            max_lax = max(laxities)
        except ValueError:
            min_lax = 0
            max_lax = 0
        laxity_range = max_lax - min_lax

        if abs(laxity_range) < epsilon:
            return 0.5
        return (self.laxity - min_lax) * prange / (laxity_range + epsilon)

    def update_relaxation(self, active_tasks, now, alpha, beta):
        normalized_l = self.normalized_laxity(active_tasks, now)
        # Combine normalized laxity and priority according to given alpha and beta
        self.relaxation = alpha * normalized_l + beta * self.priority
        return self.relaxation

    def __repr__(self):
        return f'Task: {self.id}, DL: {self.deadline}, PR: {self.priority}, Remaining: {self.remaining_time}'

    def __lt__(self, other):
        print('%')