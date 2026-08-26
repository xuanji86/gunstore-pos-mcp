"""Guards in safety.py — the credential backstop and the never-writes layer.

This file did not exist before PR-4a. Its absence is why a gap in
`_CREDENTIAL_NAME` went unnoticed: the regex is the fallback for when doctype
meta cannot be fetched, which is exactly the path no other test exercises.

The two mechanisms here fail differently and are tested differently:

* **strip_passwords** removes credential fields and reports what it removed. It
  must hold up with an EMPTY meta set, because `strip_passwords` swallows a
  failed describe on purpose ("a describe hiccup must never block a legitimate
  write") — on that path the name regex is the only thing standing between a
  DevKey and the conversation.
* **check_fields_writable** refuses the whole call. Nothing is stripped,
  nothing half-applies.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from gunstore_mcp import safety
from gunstore_mcp.safety import (
	MCP_NEVER_WRITES,
	WriteRefused,
	check_fields_writable,
	strip_passwords,
)

# Every Password-type field in the platform, read out of the doctype JSON in
# apps/ffl_*. Spelled out here rather than derived so that adding a credential
# field somewhere and forgetting this file shows up as a gap, not a silent pass.
EVERY_CREDENTIAL_FIELD = [
	("api_key", "FastBound / Payroc / ShipStation Settings"),
	("consumer_key", "WooCommerce + Dealer WooCommerce Settings"),
	("consumer_secret", "WooCommerce + Dealer WooCommerce Settings"),
	("dealer_password", "RSR Settings"),
	("dev_key", "GunBroker Settings"),
	("sandbox_dev_key", "GunBroker Settings"),
	("password", "GunBroker Settings"),
	("ftp_password", "RSR Settings"),
	("fulfillment_password", "RSR Settings"),
	("osa_api_secret", "FFL Settings"),
	("provider_api_key", "FFL Settings"),
	("webhook_secret", "WooCommerce / Dealer / FastBound Settings"),
]

# Real fieldnames that contain "key" but are not secrets. RSR's key_dealer is a
# dealer tier. Stripping these would silently break legitimate writes, so the
# regex has to be narrow enough to let them through.
NOT_CREDENTIALS = ["key_dealer", "ftp_dir_keydealer", "sandbox_mode", "username",
	"end_strategy", "base_url_override", "category_map", "page_size"]


class CredentialNameRegex(unittest.TestCase):
	"""The regex itself, asserted directly rather than only through
	strip_passwords — it is the whole fallback when doctype meta is unavailable,
	so it deserves to be pinned by name."""

	def test_the_gunbroker_devkey_fields_are_matched(self):
		"""The two names from review-pr4a M-1. Before this arm they were not
		matched, and strip_passwords swallows a failed describe on purpose — so
		one describe hiccup would have put a DevKey on the wire."""
		for name in ("dev_key", "sandbox_dev_key"):
			with self.subTest(name=name):
				self.assertIsNotNone(safety._CREDENTIAL_NAME.search(name))

	def test_devkey_spelled_without_a_separator_is_matched_too(self):
		for name in ("devkey", "DevKey", "DEV-KEY"):
			with self.subTest(name=name):
				self.assertIsNotNone(safety._CREDENTIAL_NAME.search(name))

	def test_every_platform_credential_name_is_matched(self):
		for name, where in EVERY_CREDENTIAL_FIELD:
			with self.subTest(name=name, doctype=where):
				self.assertIsNotNone(safety._CREDENTIAL_NAME.search(name),
					f"{name} ({where}) escapes the credential backstop")

	def test_real_non_secret_key_names_are_not_matched(self):
		"""RSR's key_dealer / ftp_dir_keydealer are a dealer tier. A backstop
		wide enough to eat them would break legitimate writes."""
		for name in NOT_CREDENTIALS:
			with self.subTest(name=name):
				self.assertIsNone(safety._CREDENTIAL_NAME.search(name))


class CredentialBackstopWithoutMeta(unittest.TestCase):
	"""The describe-failed path: meta contributes nothing, names are all we have."""

	def setUp(self):
		# Force the fallback branch the same way a describe outage would.
		self._p = patch.object(safety, "_password_fields", side_effect=RuntimeError("describe down"))
		self._p.start()
		self.addCleanup(self._p.stop)

	def test_every_credential_field_is_stripped_on_name_alone(self):
		for field, where in EVERY_CREDENTIAL_FIELD:
			with self.subTest(field=field, doctype=where):
				clean, stripped = strip_passwords("Whatever Settings", {field: "s3cret"})
				self.assertEqual(clean, {}, f"{field} ({where}) would have been sent")
				self.assertEqual(stripped, [field])

	def test_non_secret_key_names_still_go_through(self):
		"""A backstop that eats real fields is its own kind of bug: the write
		half-applies and the caller only finds out from a note."""
		values = {name: "value" for name in NOT_CREDENTIALS}
		clean, stripped = strip_passwords("Whatever Settings", values)
		self.assertEqual(stripped, [])
		self.assertEqual(clean, values)

	def test_nested_rows_are_covered_too(self):
		clean, stripped = strip_passwords(
			"Whatever Settings", {"rows": [{"dev_key": "x", "page_size": 5}]})
		self.assertEqual(clean, {"rows": [{"page_size": 5}]})
		self.assertEqual(stripped, ["rows[].dev_key"])


class NeverWrites(unittest.TestCase):
	DT = "GunBroker Settings"

	def test_the_environment_switches_are_all_refused(self):
		"""sandbox_mode is the headline, but base_url_override defeats it on its
		own — it replaces the base URL outright, so it is an environment switch
		wearing a different name."""
		for field in ("enabled", "sandbox_mode", "base_url_override"):
			with self.subTest(field=field):
				with self.assertRaises(WriteRefused):
					check_fields_writable(self.DT, {field: 0})

	def test_credentials_money_and_irreversibility_are_refused(self):
		for field in ("dev_key", "sandbox_dev_key", "username", "password",
				"end_strategy", "check_deposit_account", "card_checkout_enabled"):
			with self.subTest(field=field):
				with self.assertRaises(WriteRefused):
					check_fields_writable(self.DT, {field: "x"})

	def test_it_refuses_rather_than_dropping_the_bad_key(self):
		"""The whole call fails. A stripped write would land the harmless half
		and report success, leaving the caller believing sandbox_mode moved."""
		with self.assertRaises(WriteRefused) as ctx:
			check_fields_writable(self.DT, {"page_size": 50, "sandbox_mode": 0})
		self.assertIn("sandbox_mode", str(ctx.exception))
		self.assertNotIn("page_size", str(ctx.exception).split("Not writable here")[0])

	def test_the_refusal_names_what_was_wrong_and_what_the_rule_is(self):
		with self.assertRaises(WriteRefused) as ctx:
			check_fields_writable(self.DT, {"dev_key": "x", "sandbox_mode": 1})
		msg = str(ctx.exception)
		self.assertIn("'dev_key'", msg)
		self.assertIn("'sandbox_mode'", msg)
		for field in MCP_NEVER_WRITES[self.DT]:
			self.assertIn(field, msg)

	def test_ordinary_gunbroker_fields_are_untouched(self):
		check_fields_writable(self.DT, {"page_size": 50, "max_pictures": 8,
			"request_timeout_seconds": 30, "postal_code": "75206"})

	def test_child_rows_are_not_searched(self):
		"""A category_map row with its own `enabled` column is a different field
		from the Single's environment switch; matching on it would refuse
		writes that are perfectly fine."""
		check_fields_writable(self.DT, {"category_map": [{"enabled": 1}]})

	def test_doctypes_without_a_rule_are_unaffected(self):
		check_fields_writable("WooCommerce Settings", {"enabled": 0, "sandbox_mode": 1})


if __name__ == "__main__":
	unittest.main()
