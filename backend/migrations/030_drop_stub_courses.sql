-- Three one-phase stubs off the Courses page, 2026-09-18.
--
-- "database schema design principles", "databases" and "own production code
-- understanding" were single phases on the study platform, not courses. The
-- storage course teaches the same ground in four phases. They are excluded in
-- hq.courses_spec as well, so a sync cannot bring them back.

DELETE FROM hq.course_phases
 WHERE course IN ('database-schema-design-principles', 'databases',
                  'own-production-code-understanding');

DELETE FROM hq.courses
 WHERE course IN ('database-schema-design-principles', 'databases',
                  'own-production-code-understanding');
