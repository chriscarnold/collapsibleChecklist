// construct selector of checklists from python list "templates"
var clist = `<select id="checklists">
				<option value="default">Insert CHECKLIST</option>
			`;

for (var i = 0, l = templates.length; i < l; i++) {
	clist += "<option>" + templates[i] + "</option>";
}

clist += "</select>";


$(document).ready(function () {

	// insert list after image tool buttom
	$(".trac-properties .trac-wikitoolbar-img:lt(1)").after(clist);


	// insert macro on list selection
	$("#checklists").change(function () {

		// get selected option string (wiki page url)
		var wiki = $("#checklists option:selected").html();
		var macro = "[[Checklist(" + wiki + ")]]";

		// append macro to edit area content
		var box = $("#field-description");
		box.val(box.val() + "\n" + macro + "\n\n");

		// reset selector
		$("#checklists").val('default');

		// return focus to edit box
		box.focus();

	});

});
