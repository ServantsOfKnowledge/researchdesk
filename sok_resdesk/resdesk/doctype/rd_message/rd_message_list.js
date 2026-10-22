// Messages from visitors: new ones stand out.
frappe.listview_settings["RD Message"] = {
	get_indicator(doc) {
		return {
			New: [__("New"), "orange", "status,=,New"],
			Read: [__("Read"), "blue", "status,=,Read"],
			Replied: [__("Replied"), "green", "status,=,Replied"],
			Done: [__("Done"), "gray", "status,=,Done"],
			Spam: [__("Spam"), "red", "status,=,Spam"],
		}[doc.status];
	},
};
