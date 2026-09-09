-- A referral stage between shortlisting a role and applying to it.
--
-- Shortlisting already dispatches operator to find the person to ask, so
-- there was a stage of the owner's real process with nowhere to sit: the role
-- is not just "worth applying to" any more, and it is not "applied" either —
-- it is waiting on a person. Without the stage those roles sat in Shortlisted
-- and the column stopped meaning anything.

ALTER TABLE hq.jobs DROP CONSTRAINT IF EXISTS jobs_status_check;

ALTER TABLE hq.jobs ADD CONSTRAINT jobs_status_check
    CHECK (status = ANY (ARRAY[
        'seen', 'shortlisted', 'referral', 'applied',
        'interviewing', 'offer', 'rejected', 'closed'
    ]));
