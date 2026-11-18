# -----------------------------------------------------------------------------
# Route53 zone policies for cert-manager
# -----------------------------------------------------------------------------

locals {
  cert_manager_policies = {
    "cert_manager_policy_oac_prod_workload0" = {
      zone_name          = "hcp.oac.massopen.cloud",
      cluster_subdomain  = "oac-prod-workload0.hcp.oac.massopen.cloud"
      policy_name        = "cert-manager-oac-prod-workload0"
      policy_description = "modify records in hcp.oac.massopen.cloud for dns01 challenges"
    }
    "cert_manager_policy_oac_prod_infra" = {
      zone_name          = "ocp.massopen.cloud"
      cluster_subdomain  = "infra.oac.ocp.massopen.cloud"
      policy_name        = "cert-manager-oac-prod-infra"
      policy_description = "modify records in infra.oac.ocp.massopen.cloud for dns01 challenges."
      # The hcp/hcp-int records live in their own delegated hosted zones;
      # listing them here grants record changes in those zones and implicitly
      # permits _acme-challenge.*.<zone> challenges for each.
      additional_zone_names = [
        "hcp.oac.massopen.cloud",
        "hcp-int.oac.massopen.cloud"
      ]
    }
    "cert_manager_policy_dizzy" = {
      zone_name          = "int.massopen.cloud"
      cluster_subdomain  = "dizzy.int.massopen.cloud"
      policy_name        = "cert-manager-dizzy"
      policy_description = "modify records in dizzy.int.massopen.cloud for dns01 challenges."
      # The hcp/hcp-int records live in their own delegated hosted zones;
      # listing them here grants record changes in those zones and implicitly
      # permits _acme-challenge.*.<zone> challenges for each.
      additional_zone_names = [
        "dizzy-int.int.massopen.cloud",
        "dizzy-ext.int.massopen.cloud",
      ]
    }
    "cert_manager_policy_storage_massopen" = {
      zone_name          = "massopen.cloud"
      policy_name        = "cert-manager-storage-massopen-cloud"
      policy_description = "allow issuing certificate for storage.massopen.cloud object storage proxy"
      additional_challenge_names = [
        "storage.massopen.cloud"
      ]
    }
    "cert_manager_policy_infra_ocp_massopen" = {
      cluster_subdomain  = "infra.ocp.massopen.cloud"
      zone_name          = "ocp.massopen.cloud"
      policy_name        = "cert-manager-infra-ocp-massopen-cloud"
      policy_description = "modify records in infra.ocp.massopen.cloud for dns01 challenges."
    }
    "cert_manager_policy_staging_ocp_massopen" = {
      cluster_subdomain  = "staging.ocp.massopen.cloud"
      zone_name          = "ocp.massopen.cloud"
      policy_name        = "cert-manager-staging-ocp-massopen-cloud"
      policy_description = "modify records in staging.ocp.massopen.cloud for dns01 challenges."
    }
    "cert_manager_policy_moc_infra_massopen" = {
      cluster_subdomain  = "moc-infra.massopen.cloud"
      zone_name          = "massopen.cloud"
      policy_name        = "cert-manager-moc-infra-massopen-cloud"
      policy_description = "modify records in moc-infra.massopen.cloud for dns01 challenges."
    }
    "cert_manager_policy_esi_massopen" = {
      cluster_subdomain  = "esi.massopen.cloud"
      zone_name          = "massopen.cloud"
      policy_name        = "cert-manager-esi-massopen-cloud"
      policy_description = "modify records for esi.massopen.cloud for dns01 challenges."
    }
    "cert_manager_policy_oac_dev_infra" = {
      cluster_subdomain  = "infra.oac.int.massopen.cloud"
      zone_name          = "int.massopen.cloud"
      policy_name        = "cert-manager-oac-infra-int-massopen-cloud"
      policy_description = "modify records in infra.oac.int.massopen.cloud for dns01 challenges."
      additional_zone_names = [
        "hcp.oac.int.massopen.cloud",
        "hcp-int.oac.int.massopen.cloud"
      ]
    }
    "cert_manager_policy_oac_dev_workload0" = {
      cluster_subdomain  = "oac-dev-workload0.hcp.oac.int.massopen.cloud"
      zone_name          = "hcp.oac.int.massopen.cloud"
      policy_name        = "cert-manager-oac-dev-workload0-int-massopen-cloud"
      policy_description = "modify records for oac-prod hosted cluster dns01 challenges."
    }
    "cert_manager_policy_oac_dev_workload1" = {
      cluster_subdomain  = "oac-dev-workload1.hcp.oac.int.massopen.cloud"
      zone_name          = "hcp.oac.int.massopen.cloud"
      policy_name        = "cert-manager-oac-dev-workload1-int-massopen-cloud"
      policy_description = "modify records for oac-dev-workload1 hosted cluster dns01 challenges."
    }
    "cert_manager_policy_oac_dev_workload2" = {
      cluster_subdomain  = "oac-dev-workload2.hcp.oac.int.massopen.cloud"
      zone_name          = "hcp.oac.int.massopen.cloud"
      policy_name        = "cert-manager-oac-dev-workload2-int-massopen-cloud"
      policy_description = "modify records for oac-dev-workload2 hosted cluster dns01 challenges."
    }
    "cert_manager_policy_jetty" = {
      cluster_subdomain  = "jetty.oac.int.massopen.cloud"
      zone_name          = "int.massopen.cloud"
      policy_name        = "cert-manager-jetty-int-massopen-cloud"
      policy_description = "modify records in jetty.oac.int.massopen.cloud for dns01 challenges."
    }
    "cert_manager_policy_nist_dev_infra" = {
      cluster_subdomain  = "nist-dev-infra.nist.int.massopen.cloud"
      zone_name          = "nist.int.massopen.cloud"
      policy_name        = "cert-manager-nist-dev-infra-int-massopen-cloud"
      policy_description = "modify records in nist-dev-infra.nist.int.massopen.cloud for dns01 challenges."
      additional_zone_names = [
        "hcp.nist.int.massopen.cloud",
        "hcp-int.nist.int.massopen.cloud"
      ]
    }
    "cert_manager_policy_nist_dev_workload0" = {
      cluster_subdomain  = "nist-dev-workload0.hcp.nist.int.massopen.cloud"
      zone_name          = "hcp.nist.int.massopen.cloud"
      policy_name        = "cert-manager-nist-dev-workload0-int-massopen-cloud"
      policy_description = "modify records for nist-dev-workload0 hosted cluster dns01 challenges."
    }
    "cert_manager_policy_compliant_dev_infra" = {
      cluster_subdomain  = "compliant-dev-infra.nist.int.massopen.cloud"
      zone_name          = "nist.int.massopen.cloud"
      policy_name        = "cert-manager-compliant-dev-infra-int-massopen-cloud"
      policy_description = "modify records in compliant-dev-infra.nist.int.massopen.cloud for dns01 challenges."
      additional_zone_names = [
        "hcp.nist.int.massopen.cloud",
        "hcp-int.nist.int.massopen.cloud"
      ]
    }
    "cert_manager_policy_compliant_dev_workload0" = {
      cluster_subdomain  = "compliant-dev-workload0.hcp.nist.int.massopen.cloud"
      zone_name          = "hcp.nist.int.massopen.cloud"
      policy_name        = "cert-manager-compliant-dev-workload0-int-massopen-cloud"
      policy_description = "modify records for compliant-dev-workload0 hosted cluster dns01 challenges."
    }
    "cert_manager_policy_bu_ist_demo_infra" = {
      cluster_subdomain  = "bu-ist-demo.int.massopen.cloud"
      zone_name          = "int.massopen.cloud"
      policy_name        = "cert-manager-bu-ist-demo-infra-int-massopen-cloud"
      policy_description = "modify records in bu-ist-demo.int.massopen.cloud for dns01 challenges."
      additional_zone_names = [
        "hcp.bu-ist-demo.int.massopen.cloud",
        "hcp-int.bu-ist-demo.int.massopen.cloud"
      ]
    }
  }
}

module "cert_manager_policy" {
  for_each           = local.cert_manager_policies
  source             = "./modules/iam-policy/cert-manager-route53"
  cluster_subdomain  = try(each.value.cluster_subdomain, null)
  policy_name        = each.value.policy_name
  policy_description = each.value.policy_description

  # All hosted zones referenced here (primary and additional) are managed in
  # hosted-zones.tf, in this same root module -- so look up ARNs directly
  # from the zone resources rather than by name. This avoids a data-source
  # lookup racing the zone's own creation when both are applied together.
  zone_arn                   = aws_route53_zone.this[each.value.zone_name].arn
  additional_challenge_names = try(each.value.additional_challenge_names, [])
  additional_zone_names      = try(each.value.additional_zone_names, [])
  additional_zone_arns = {
    for name in try(each.value.additional_zone_names, []) : name => aws_route53_zone.this[name].arn
  }
}
