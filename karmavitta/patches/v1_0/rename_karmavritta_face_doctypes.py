import frappe


def execute():
	"""Rename biometric DocTypes to remove Karmavritta prefix."""
	renames = [
		("Karmavritta Face Biometric", "Face Biometric"),
		("Karmavritta Face Registration Audit", "Face Registration Audit"),
	]
	for old, new in renames:
		if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
			frappe.rename_doc("DocType", old, new, force=True)
			frappe.clear_cache(doctype=new)
		elif frappe.db.exists("DocType", old) and frappe.db.exists("DocType", new):
			# Both exist after partial migrate — keep new, drop empty old if safe
			pass
