import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import app
from app import OAApp


def main() -> None:
    answers = iter(
        [
            "",  # capability definition
            "Maintain secure access",
            "Keep authorized operations available while preventing unauthorized entry.",
            "2",  # no capability limitation
            "2",  # no additional capability
            "1",  # actor
            "",  # actor definition
            "Field Coordinator",
            "Human role responsible for coordinating access decisions.",
            "2",  # no actor limitation
            "1",  # involved in capability
            "1",  # capability
            "",  # INVOLVED_IN_CAPABILITY definition
            "1",  # another participant
            "2",  # entity
            "",  # entity definition
            "Restricted Area",
            "Physical area whose access is controlled during operations.",
            "2",  # no entity limitation
            "2",  # not directly involved in capability
            "2",  # no more participants
            "",  # activity definition
            "Verify access authorization",
            "Confirm that presented authorization permits entry.",
            "2",  # no activity limitation
            "1",  # performer
            "",  # PERFORMS definition
            "2",  # no other performer
            "1",  # capability
            "",  # SUPPORTS_CAPABILITY definition
            "1",  # another activity
            "Permit authorized entry",
            "Allow an authorized person to enter the restricted area.",
            "2",  # no activity limitation
            "1",  # performer
            "2",  # no other performer
            "1",  # capability
            "2",  # no more activities
            "1",  # create exchange
            "",  # exchange definition
            "Access authorization data",
            "Authorization evidence transferred to the entry activity.",
            "2",  # no exchange limitation
            "1",  # source activity
            "1",  # target activity
            "",  # SOURCE_ACTIVITY definition
            "",  # TARGET_ACTIVITY definition
            "2",  # no more exchanges
            "1",  # create communication mean
            "",  # communication mean definition
            "Voice radio communication",
            "Operational voice channel between the field participants.",
            "2",  # no communication limitation
            "1",  # source participant
            "1",  # target participant
            "",  # SOURCE_PARTICIPANT definition
            "",  # TARGET_PARTICIPANT definition
            "1",  # supports an exchange
            "1",  # select exchange
            "",  # SUPPORTS_EXCHANGE definition
            "2",  # no more communication means
            "2",  # actor not structurally contained by area
            "1",  # actor located in area
            "1",  # select area
            "",  # LOCATED_IN definition
            "2",  # capability not refined now
            "2",  # area not decomposed now
            "2",  # first activity not decomposed
            "2",  # second activity not decomposed
            "2",  # exchange not refined
            "2",  # communication mean not refined
            "7",  # finish
        ]
    )

    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "oa_model.json"
        with patch.object(app, "DEFAULT_SAVE_PATH", target), patch(
            "builtins.input", side_effect=lambda _prompt="": next(answers)
        ), redirect_stdout(io.StringIO()):
            builder = OAApp()
            builder.run()

        assert target.exists()
        assert len(builder.model.nodes_of_type("OperationalCapability")) == 1
        assert len(builder.model.nodes_of_type("OperationalActor")) == 1
        assert len(builder.model.nodes_of_type("OperationalEntity")) == 1
        assert len(builder.model.nodes_of_type("OperationalActivity")) == 2
        assert len(builder.model.nodes_of_type("OperationalExchange")) == 1
        assert len(builder.model.nodes_of_type("CommunicationMean")) == 1
        assert not builder.model.completeness_messages()

    try:
        next(answers)
    except StopIteration:
        pass
    else:
        raise AssertionError("The scripted flow did not consume every answer.")

    print("App flow test passed.")


if __name__ == "__main__":
    main()
