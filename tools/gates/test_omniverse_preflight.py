import unittest
from tools.omniverse_preflight import driver_status, gates, parse_gpus, MIN_DISK, MIN_RAM


class PreflightTest(unittest.TestCase):
    def ready(self, **overrides):
        args = dict(gpus=[dict(model="RTX 3090", driver_status="pass", processes_known=True, processes=[])],
                    os_info={"ID": "ubuntu", "VERSION_ID": "24.04"},
                    disk={"available_bytes": MIN_DISK}, available_ram=MIN_RAM, display=None)
        args.update(overrides)
        return gates(**args)

    def test_boundary_and_headless(self):
        self.assertTrue(all(self.ready().values()))
        self.assertFalse(self.ready(disk={"available_bytes": MIN_DISK - 1})["kit_storage"])
        self.assertFalse(self.ready(available_ram=MIN_RAM - 1)["ram"])

    def test_unknown_gpu_blocks(self):
        self.assertIsNone(parse_gpus({"returncode": 1}))
        self.assertFalse(self.ready(gpus=None)["unused_rtx"])

    def test_newer_driver_is_not_pass(self):
        self.assertEqual(driver_status("550.54.14"), "fail")
        self.assertEqual(driver_status("570.170"), "unverified")
        self.assertEqual(driver_status("595.58.03"), "pass")
        self.assertEqual(driver_status("N/A"), "unknown")

    def test_busy_graphics_and_compute_are_not_available(self):
        for kind in ("G", "C"):
            gpu = dict(model="RTX 3090", driver_status="pass", processes_known=True, processes=[{"type": kind}])
            self.assertFalse(self.ready(gpus=[gpu])["unused_rtx"])

    def test_os_blocks_even_when_everything_else_passes(self):
        self.assertFalse(self.ready(os_info={"ID": "ubuntu", "VERSION_ID": "20.04"})["os"])

    def test_nvml_process_visibility(self):
        template = '<nvidia_smi_log><driver_version>570.169</driver_version><gpu><product_name>RTX 3090</product_name><processes>{}</processes></gpu></nvidia_smi_log>'
        for content, known in (("N/A", False), ("", True)):
            gpu = parse_gpus({"returncode": 0, "stdout": template.format(content)})[0]
            self.assertEqual(gpu["processes_known"], known)


if __name__ == "__main__":
    unittest.main()
