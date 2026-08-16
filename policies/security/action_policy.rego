package project_pipeline.security

default allow := false

allow if {
  input.authorized == true
  input.high_impact == false
}

allow if {
  input.authorized == true
  input.high_impact == true
  input.independent_approval == true
}

deny contains reason if {
  input.authorized != true
  reason := "identity is not authorized for requested capability and scope"
}

deny contains reason if {
  input.high_impact == true
  input.independent_approval != true
  reason := "high-impact action lacks independent approval"
}
