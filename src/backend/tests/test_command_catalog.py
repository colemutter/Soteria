from __future__ import annotations

import copy
import unittest

from pydantic import ValidationError

from agent.command_catalog import (
    CatalogCommandStatus,
    CommandCatalog,
    find_catalog_commands,
    get_catalog_command,
    load_command_catalog,
)


class CommandCatalogTest(unittest.TestCase):
    def test_real_catalog_loads_with_expected_metadata(self) -> None:
        catalog = load_command_catalog()

        self.assertEqual(
            catalog.catalog_version,
            "nos3-openc3-v1_07_04-cmdcat.20260621",
        )
        self.assertEqual(catalog.simulator_stack, "nos3_openc3")
        self.assertGreaterEqual(len(catalog.commands), 10)

    def test_known_command_ids_resolve(self) -> None:
        sample_disable = get_catalog_command("sample_disable")
        radio_enable = get_catalog_command("radio_enable_output")
        adcs_mode = get_catalog_command("adcs_set_sunsafe")

        self.assertEqual(sample_disable.target, "SAMPLE_RADIO")
        self.assertEqual(sample_disable.command, "SAMPLE_DISABLE_CC")
        self.assertEqual(radio_enable.args[0].default, "radio-sim")
        self.assertEqual(radio_enable.args[1].default, 5011)
        self.assertEqual(adcs_mode.target, "GENERIC_ADCS")
        self.assertEqual(adcs_mode.command, "GENERIC_ADCS_SET_MODE_CC")
        self.assertEqual(adcs_mode.args[0].value, "SUNSAFE_MODE")

    def test_unresolved_commands_are_not_selected_as_executable(self) -> None:
        unresolved = find_catalog_commands(status=CatalogCommandStatus.UNRESOLVED)
        executable = find_catalog_commands(automated_allowed=True)

        self.assertEqual(
            [command.id for command in unresolved],
            ["eps_load_shed_policy"],
        )
        self.assertNotIn(
            "eps_load_shed_policy",
            {command.id for command in executable},
        )
        self.assertNotIn(
            "radiation_protect_generic",
            {command.id for command in executable},
        )
        self.assertTrue(all(command.is_executable for command in executable))

    def test_duplicate_command_ids_fail_validation(self) -> None:
        payload = load_command_catalog().model_dump(mode="json")
        duplicate = copy.deepcopy(payload["commands"][0])
        payload["commands"].append(duplicate)

        with self.assertRaisesRegex(ValidationError, "duplicate command IDs"):
            CommandCatalog.model_validate(payload)

    def test_default_must_be_allowed_when_allowed_values_exist(self) -> None:
        payload = load_command_catalog().model_dump(mode="json")
        payload["commands"][1]["args"][1]["default"] = 9999

        with self.assertRaisesRegex(ValidationError, "allowed_values"):
            CommandCatalog.model_validate(payload)

    def test_unresolved_command_cannot_be_marked_automated(self) -> None:
        payload = load_command_catalog().model_dump(mode="json")
        payload["commands"][-1]["automated_allowed"] = True

        with self.assertRaisesRegex(ValidationError, "unresolved commands"):
            CommandCatalog.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
