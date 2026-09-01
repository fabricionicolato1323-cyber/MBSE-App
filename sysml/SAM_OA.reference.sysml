// SAM OA reference library extracted from a SAM-exported SysML v2 project.
//
// This file is intentionally instance-free. It captures only the reusable
// definition structure observed in the SAM export. Example model names, IDs,
// participants, activities, capabilities, exchanges, and scenarios must never
// be copied into application logic.
//
// NOTE: the exported package name below preserves the spelling produced by the
// reference SAM export. The Python implementation must obtain it from the
// declarative profile instead of hardcoding it.

package Arcadia_OA_libray {
    action def 'Operational Scenario';

    part def 'Operational Entity';
    part def 'Operational Actor' :> 'Operational Entity';

    requirement def 'Operational Capability' {
        subject subj;
    }

    flow def 'Operational Iteration' {
        end reference a;
        end reference b;
    }

    interface def 'Communication Mean' {
        end source;
        end target;
    }

    constraint def 'Operational Constraint';
    action def 'Operational Activity';
}
