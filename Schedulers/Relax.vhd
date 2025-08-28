library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;
library UNISIM;
use UNISIM.VComponents.all;
entity relax_scheduler is
    generic (
        NUM_CORES        : integer := 2;
        MAX_TASKS        : integer := 16;
        TASK_ID_WIDTH    : integer := 8;
        TIME_WIDTH       : integer := 32;
        PRIORITY_WIDTH   : integer := 2
    );
    port (
        clk             : in  std_logic;
        reset           : in  std_logic;
        
        -- System time
        sys_time        : in  std_logic_vector(TIME_WIDTH-1 downto 0);
        
        -- Task input (ID[7:0], Priority[9:8], Burst[41:10], Deadline[73:42])
        task_in         : in  std_logic_vector(73 downto 0);
        task_valid      : in  std_logic;
        task_ready      : inout std_logic;  -- handshake
        
        -- Core-task outputs
        core_status     : out std_logic_vector(NUM_CORES*TASK_ID_WIDTH-1 downto 0);
        deadline_misses : out std_logic_vector(31 downto 0);
        cpu_util        : out std_logic_vector(31 downto 0)
    );
end relax_scheduler;
architecture Behavioral of relax_scheduler is
    signal clk_bufg : std_logic;
    -- Task and core records
    type task_t is record
        id          : std_logic_vector(TASK_ID_WIDTH-1 downto 0);
        priority    : unsigned(PRIORITY_WIDTH-1 downto 0);
        arrival     : unsigned(TIME_WIDTH-1 downto 0);
        burst       : unsigned(TIME_WIDTH-1 downto 0);
        deadline    : unsigned(TIME_WIDTH-1 downto 0);
        remaining   : unsigned(TIME_WIDTH-1 downto 0);
        assigned_core: integer range -1 to NUM_CORES-1;
        running     : std_logic;
        started     : std_logic;
        finished    : std_logic;
        laxity      : integer;
        relaxation  : integer;
        valid       : std_logic;
    end record;
    type task_array_t is array(0 to MAX_TASKS-1) of task_t;
    type core_t is record
        task_idx    : integer range -1 to MAX_TASKS-1;
        busy_until  : unsigned(TIME_WIDTH-1 downto 0);
        active      : std_logic;
    end record;
    type core_array_t is array(0 to NUM_CORES-1) of core_t;
    -- Internal signals
    signal tasks          : task_array_t;
    signal cores          : core_array_t;
    signal tick           : unsigned(TIME_WIDTH-1 downto 0) := (others=>'0');
    signal deadline_miss_cnt : unsigned(31 downto 0) := (others=>'0');
    signal total_busy     : unsigned(63 downto 0) := (others=>'0');
    signal current_time   : unsigned(TIME_WIDTH-1 downto 0);
    -- Constants for relaxation weights
    constant alpha_num : integer := 7;
    constant alpha_den : integer := 10;
    constant beta_num  : integer := 3;
    constant beta_den  : integer := 10;
begin
    -- Instantiate the clock buffer
    clk_buf_inst : BUFG
        port map (
            I => clk,
            O => clk_bufg
        );
    -- Task input handshake: ready when task slots exist
    task_ready <= '1' when (tasks(MAX_TASKS-1).valid = '0') else '0';
    -- Scheduler main process using buffered clock
    process(clk_bufg, reset)
        variable i, j            : integer;
        variable min_rela        : integer;
        variable sel_task        : integer;
        variable this_laxity     : integer;
        variable this_relax      : integer;
    begin
        if reset = '1' then
            -- Reset all tasks
            for i in 0 to MAX_TASKS-1 loop
                tasks(i).id         <= (others => '0');
                tasks(i).priority   <= (others => '0');
                tasks(i).arrival    <= (others => '0');
                tasks(i).burst      <= (others => '0');
                tasks(i).deadline   <= (others => '0');
                tasks(i).remaining  <= (others => '0');
                tasks(i).assigned_core <= -1;
                tasks(i).running    <= '0';
                tasks(i).started    <= '0';
                tasks(i).finished   <= '0';
                tasks(i).laxity     <= 0;
                tasks(i).relaxation <= 0;
                tasks(i).valid      <= '0';
            end loop;
            -- Reset cores
            for j in 0 to NUM_CORES-1 loop
                cores(j).task_idx   <= -1;
                cores(j).busy_until <= (others=>'0');
                cores(j).active     <= '0';
            end loop;
            deadline_miss_cnt <= (others => '0');
            total_busy        <= (others=>'0');
            tick              <= (others=>'0');
        elsif rising_edge(clk_bufg) then
            current_time <= unsigned(sys_time);
            -- Accept new tasks if valid & slot available
            if task_valid = '1' and task_ready = '1' then
                for i in 0 to MAX_TASKS-1 loop
                    if tasks(i).valid = '0' then
                        tasks(i).id        <= task_in(7 downto 0);
                        tasks(i).priority  <= unsigned(task_in(9 downto 8));
                        tasks(i).burst     <= unsigned(task_in(41 downto 10));
                        tasks(i).arrival   <= unsigned(sys_time);
                        tasks(i).deadline  <= unsigned(task_in(73 downto 42));
                        tasks(i).remaining <= unsigned(task_in(41 downto 10));
                        tasks(i).assigned_core <= -1;
                        tasks(i).running   <= '0';
                        tasks(i).started   <= '0';
                        tasks(i).finished  <= '0';
                        tasks(i).valid     <= '1';
                        exit;
                    end if;
                end loop;
            end if;
            -- Update per-task status & calculate laxity, relaxation
            for i in 0 to MAX_TASKS-1 loop
                if tasks(i).valid = '1' and tasks(i).finished = '0' then
                    this_laxity := to_integer(tasks(i).deadline) -
                                   (to_integer(current_time) + to_integer(tasks(i).remaining));
                    tasks(i).laxity <= this_laxity;
                    this_relax := (alpha_num * this_laxity) / alpha_den +
                                  (beta_num * to_integer(tasks(i).priority)) / beta_den;
                    tasks(i).relaxation <= this_relax;
                end if;
            end loop;
            -- Free up finished cores, set tasks as finished, count deadline misses
            for j in 0 to NUM_CORES-1 loop
                if cores(j).active = '1' and cores(j).task_idx /= -1 then
                    i := cores(j).task_idx;
                    if tasks(i).valid = '1' and
                       (to_integer(tasks(i).remaining) = 0 or to_integer(cores(j).busy_until) <= to_integer(current_time)) then
                        tasks(i).finished   <= '1';
                        tasks(i).running    <= '0';
                        cores(j).task_idx   <= -1;
                        cores(j).active     <= '0';
                        if to_integer(tasks(i).deadline) < to_integer(current_time) then
                            deadline_miss_cnt <= (unsigned(deadline_miss_cnt) + 1);
                        end if;
                    end if;
                end if;
            end loop;
            -- Assign ready tasks with minimum relaxation to free cores
            for j in 0 to NUM_CORES-1 loop
                if cores(j).active = '0' then
                    min_rela  := 2147483647;
                    sel_task  := -1;
                    for i in 0 to MAX_TASKS-1 loop
                        if tasks(i).valid = '1' and
                           tasks(i).finished = '0' and
                           tasks(i).running = '0' and
                           to_integer(tasks(i).arrival) <= to_integer(current_time) and
                           tasks(i).laxity >= 0 then
                            if tasks(i).relaxation < min_rela then
                                min_rela := tasks(i).relaxation;
                                sel_task := i;
                            end if;
                        end if;
                    end loop;
                    if sel_task /= -1 then
                        tasks(sel_task).assigned_core <= j;
                        tasks(sel_task).running       <= '1';
                        tasks(sel_task).started       <= '1';
                        cores(j).active               <= '1';
                        cores(j).task_idx             <= sel_task;
                        cores(j).busy_until           <= unsigned(current_time) + tasks(sel_task).burst;
                        total_busy <= total_busy + tasks(sel_task).burst;
                    end if;
                end if;
            end loop;
            -- Advance running tasks per clock tick
            for j in 0 to NUM_CORES-1 loop
                if cores(j).active = '1' and cores(j).task_idx /= -1 then
                    i := cores(j).task_idx;
                    if tasks(i).remaining > 0 then
                        tasks(i).remaining <= tasks(i).remaining - 1;
                    end if;
                end if;
            end loop;
            tick <= tick + 1;
        end if;
    end process;
    -- Compose output signals
    gen_core_output: for j in 0 to NUM_CORES-1 generate
        core_status((j+1)*TASK_ID_WIDTH-1 downto j*TASK_ID_WIDTH) <=
            (others=>'0') when cores(j).task_idx = -1 else tasks(cores(j).task_idx).id;
    end generate;
    deadline_misses <= std_logic_vector(deadline_miss_cnt);
    cpu_util <= std_logic_vector(resize(total_busy(31 downto 0) * 100 / (tick + 1), 32));
end Behavioral;
