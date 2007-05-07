

class Job:
    def __init__(self, job_id, user_predicted_duration, job_nodes, \
                 job_arrival_time=0, job_actual_duration=0, job_admin_QoS=0, job_user_QoS=0):
        
        #assert job_nodes > 0
        #assert job_actual_duration >= 0
        #assert user_predicted_duration >= job_actual_duration
        #assert job_arrival_time >= 0
        
        self.id = job_id
        self.user_predicted_duration = user_predicted_duration
        self.nodes = job_nodes
        self.arrival_time = job_arrival_time # Assumption: arrival time is greater than zero 
        self.start_to_run_at_time = -1 
        self.actual_duration = job_actual_duration

        # the next are essentially for the MauiScheduler
        self.admin_QoS = job_admin_QoS # the priority given by the system administration  
        self.user_QoS = job_user_QoS # the priority given by the user
        self.maui_bypass_counter = 0
        self.maui_timestamp = 0
        

    def __str__(self):
        return "job_id=" + str(self.id) + ", arrival=" + str(self.arrival_time) + \
               ", dur=" + str(self.user_predicted_duration) + ",act_dur=" + str(self.actual_duration) + \
               ", #nodes=" + str(self.nodes) + \
               ", startTime=" + str(self.start_to_run_at_time)  
    
        

class CpuTimeSlice:
    ''' represents a "tentative feasible" snapshot of the cpu between the start_time until start_time + dur_time.
        It is tentative since a job might be rescheduled to an earlier slice. It is feasible since the total demand
        for nodes ba all the jobs assigned to this slice never exceeds the amount of the total nodes available.
        Assumption: the duration of the slice is never changed.
        We can replace this slice with a new slice with shorter duration.'''
    
    total_nodes = 0 # a class variable
    
    def __init__(self, free_nodes, start_time=0, duration=1):
        #assert duration > 0
        #assert start_time >= 0
        
        self.free_nodes = free_nodes
        self.start_time = start_time
        self.duration = duration
                
            
    def addJob(self, job_nodes):
        # assert self.free_nodes >= job_nodes
        self.free_nodes -= job_nodes


    def delJob(self, job_nodes):
        self.free_nodes += job_nodes
        # assert self.free_nodes <= CpuTimeSlice.total_nodes



    def __str__(self):
        return '%d %d %d' % (self.start_time, self.duration, self.free_nodes)


        
        
class CpuSnapshot(object):
    """ represents the time table with the assignments of jobs to available nodes. """
    
    def __init__(self, total_nodes=100):
        CpuTimeSlice.total_nodes = total_nodes
        self.total_nodes = total_nodes
        self.slices=[] # initializing the main structure of this class 
        self.slices.append(CpuTimeSlice(self.total_nodes)) # Assumption: the snapshot always has at least one slice 
        self.archive_of_old_slices=[]
               

    def jobEarliestAssignment(self, job, time=0):
        """ returns the earliest time right after the given time for which the job can be assigned
        enough nodes for job.user_predicted_duration unit of times in an uninterrupted fashion.
        Assumption: number of requested nodes is not greater than number of total nodes.
        Assumption: time >=  the arrival time of the job >= 0."""
        
        partially_assigned = False         
        tentative_start_time = 0 
        accumulated_duration = 0
        
        assert time >= 0
        
        for s in self.slices: # continuity assumption: if t' is the successor of t, then: t' = t + duration_of_slice_t
            
            end_of_this_slice = s.start_time +  s.duration

            feasible = end_of_this_slice > time and s.free_nodes >= job.nodes
            
            if not feasible: # then surely the job cannot be assigned to this slice
                partially_assigned = False
                accumulated_duration = 0
                        
            elif feasible and not partially_assigned:
                # we'll check if the job can be assigned to this slice and perhaps to its successive 
                partially_assigned = True
                tentative_start_time =  max(time, s.start_time)
                accumulated_duration = end_of_this_slice - tentative_start_time

            else:
                # it's a feasible slice and the job is partially_assigned:
                accumulated_duration += s.duration
            
            if accumulated_duration >= job.user_predicted_duration:
                return tentative_start_time
    
            # end of for loop, we've examined all existing slices
            
        if partially_assigned: #and so there are not enough slices in the tail, then:
            return tentative_start_time

        # otherwise, the job will be assigned right after the last slice or later
        last = self.slices[len(self.slices)-1]
        last_slice_end_time =  last.start_time + last.duration
        return max(time, last_slice_end_time)  



    def _ensure_a_slice_starts_at(self, start_time):
        """ A preprocessing stage. Usage: 
        First, to ensure that the assignment time of the new added job will start at a beginning of a slice.
        Second, to ensure that the actual end time of the job will end at the ending of slice.
        we need this when we add a new job, or delete a tail of job when the user estimation is larger than the actual
        duration. """

        for s in self.slices:
            if s.start_time > start_time:
                break
            if s.start_time == start_time:  
                return # we already have such a slice

        last = self.slices[len(self.slices)-1]
        last_slice_end_time =  last.start_time + last.duration
        

        if last_slice_end_time < start_time: #we add an intermediate "empty" slice to maintain the "continuity" of slices
            self.slices.append( CpuTimeSlice(self.total_nodes, last_slice_end_time, start_time - last_slice_end_time) )
            self.slices.append( CpuTimeSlice(self.total_nodes, start_time, 1) ) # duration is arbitrary here
            return
        
        if last_slice_end_time == start_time:
            self.slices.append( CpuTimeSlice(self.total_nodes, start_time, 1) ) # duration is arbitrary here
            return


        index = 0
        for s in self.slices:
            index += 1
            
            end_of_this_slice = s.start_time +  s.duration
            duration_of_this_slice = s.duration
            
            if end_of_this_slice < start_time:
                continue
            
            # splitting slice s with respect to the start time
            del self.slices[index-1]
            self.slices.insert( index-1, CpuTimeSlice(s.free_nodes, s.start_time, start_time - s.start_time) )
            self.slices.insert( index, CpuTimeSlice(s.free_nodes, start_time, end_of_this_slice - start_time) )
            return


      
    def _add_job_to_relevant_slices(self, job):
        assignment_time = job.start_to_run_at_time     
        remained_duration = job.user_predicted_duration

        index = 0
        for s in self.slices:
            index += 1
            if s.start_time < assignment_time:
                continue
            
            if  s.duration <= remained_duration: # just add the job to the current slice
                s.addJob(job.nodes)
                remained_duration -= s.duration
                if remained_duration == 0:
                    return
                continue            
                   
            #else: duration_of_this_slice > remained_duration, that is the current slice
            #is longer than what we actually need, we thus split the slice, then add the job to the 1st one, and return

            del self.slices[index-1]
            self.slices.insert(index-1, 
                CpuTimeSlice(free_nodes = s.free_nodes,
                    start_time = s.start_time + remained_duration,
                    duration   = s.duration - remained_duration,
                )
                )
            
            newslice = CpuTimeSlice(free_nodes = s.free_nodes,
                start_time = s.start_time,
                duration   = remained_duration,
                )
            newslice.addJob(job.nodes)
            self.slices.insert(index-1, newslice)
            return
            
        # end of for loop, we've examined all existing slices and if this point is reached
        # we must add a new "tail" slice for the remaining part of the job

        last = self.slices[len(self.slices)-1]
        last_slice_end_time =  last.start_time + last.duration
        self.slices.append(CpuTimeSlice(self.total_nodes - job.nodes, last_slice_end_time, remained_duration))
        return
        

    def assignJob(self, job, assignment_time):         
        """ assigns the job to start at the given assignment time.        
        Important assumption: assignment_time was returned by jobEarliestAssignment. """
        job.start_to_run_at_time = assignment_time
        self._ensure_a_slice_starts_at(assignment_time)
        self._add_job_to_relevant_slices(job)

        

        
    def delJobFromCpuSlices(self, job):        
        """ Deletes an entire job from the slices. 
        Assumption: job resides at consecutive slices (no preemptions) """

        job_predicted_finish_time = job.start_to_run_at_time + job.user_predicted_duration
        job_start = job.start_to_run_at_time
        
        for s in self.slices:
            if s.start_time < job_start:
                continue
            elif s.start_time + s.duration <= job_predicted_finish_time:  
                s.delJob(job.nodes) 
            else:
                return


    def delTailofJobFromCpuSlices(self, job):
        """ This function is used when the actual duration is smaller than the predicted duration, so the tail
        of the job must be deleted from the slices.
        We itterate trough the sorted slices until the critical point is found: the point from which the
        tail of the job starts. 
        Assumption: job is assigned to successive slices. Specifically, there are no preemptions."""

        if job.actual_duration ==  job.user_predicted_duration: 
            return
        
        job_finish_time = job.start_to_run_at_time + job.actual_duration
        job_predicted_finish_time = job.start_to_run_at_time + job.user_predicted_duration
        
        self._ensure_a_slice_starts_at(job_finish_time) 
        for s in self.slices:
            if s.start_time < job_finish_time:
                continue
            elif s.start_time + s.duration <= job_predicted_finish_time:  
                s.delJob(job.nodes) 
            else:
                return

            
            
    def archive_old_slices(self, current_time):
        """ This method restores the old slices."""
        if len(self.slices) < 5:
            return
        while True:
            s = self.slices[0]  
            if s.start_time + s.duration < current_time:
                self.archive_of_old_slices.append(s)
                self.slices.pop(0)
            else:
                return
            
    def clean_empty_slices_from_the_tail(self, current_time):        
        while len(self.slices) > 3:
            s = self.slices.pop()
            if  s.free_nodes == self.total_nodes:
                continue
            else:
                self.slices.append(s)
                return
    
            
     

    def restore_old_slices(self):
        while (len(self.archive_of_old_slices) > 0):
            s = self.archive_of_old_slices.pop()
            self.slices.insert(0, s)

    
            
    def CpuSlicesTestFeasibility(self):
        self.restore_old_slices()
        duration = 0
        time = 0
        scheduled_jobs_start_slice = {}
        scheduled_jobs_last_slice = {}
        scheduled_jobs_accumulated_duration = {}
        scheduled_jobs = {}
        
        for s in self.slices:
            free_nodes = s.free_nodes
            prev_duration = duration
            prev_t = time
            
            if free_nodes < 0: 
                print ">>> PROBLEM: free nodes is a negative number, in slice", t
                return False
            
            if free_nodes > self.total_nodes:
                print ">>> PROBLEM: free nodes exceeds the number of available nodes ...."
                return False

            num_of_active_nodes = 0
            
            for job in s.jobs:
                num_of_active_nodes += job.nodes
                
                if scheduled_jobs_start_slice.has_key(job.id):
                    scheduled_jobs_last_slice[job.id] = s.start_time + s.duration
                    scheduled_jobs_accumulated_duration[job.id] += s.duration 
                else: # the first time this job is encountered  
                    if s.start_time != job.start_to_run_at_time:
                        print ">>> PROBLEM: start time: ", job.start_to_run_at_time, " of job", job.id, "is:", s.start_time
                        return False
                    scheduled_jobs[job.id] = job
                    scheduled_jobs_start_slice[job.id] = s.start_time
                    scheduled_jobs_last_slice[job.id] = s.start_time + s.duration
                    scheduled_jobs_accumulated_duration[job.id] = s.duration
                    
            if num_of_active_nodes != self.total_nodes - free_nodes:
                print ">>> PROBLEM: wrong number of free nodes in slice", s.start_time 
                return False
            
            if s.start_time != prev_t + prev_duration:
                print ">>> PROBLEM: non successive slices", s.start_time, prev_t 
                return False
                
            duration = s.duration
            time = s.start_time

        for job_id, job_start_slice in scheduled_jobs_start_slice.iteritems():
            job_last_slice =  scheduled_jobs_last_slice[job_id]
            duration_of_job = job_last_slice - job_start_slice
            if duration_of_job != scheduled_jobs[job_id].actual_duration:
                print ">>>PROBLEM: with actual duration of job: ", \
                      job.actual_duration, "vs.", duration_of_job,  " of job", job_id
                return False
        
            if scheduled_jobs_accumulated_duration[job.id] != scheduled_jobs[job.id].actual_duration:
                print ">>>PROBLEM: with actual duration of job:", \
                      scheduled_jobs_accumulated_duration[job.id], "vs.",  scheduled_jobs[job.id].actual_duration, \
                      " of job", job_id
                return False
            

        print "TEST is OK!!!!" 
        return True
    
            
            
    
             
    def printCpuSlices(self):

        print "start time | duration | #free nodes | { job.id : #job.nodes }"            
        for s in self.slices: 
            print s
        print
        

