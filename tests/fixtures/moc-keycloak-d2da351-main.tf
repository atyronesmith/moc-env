
locals {
  realm_id = "moc"
  openshift_oidc_clusters = {
    dizzy = {
      cluster_name           = "dizzy"
      openshift_redirect_uri = "https://oauth-openshift.apps.dizzy.int.massopen.cloud/oauth2callback/mocsso"
      client_secret_name     = "cluster/dizzy/keycloak-oidc"
      keycloak_client_uuid   = "dizzy"
    }
    moc_infra = {
      cluster_name           = "moc-infra"
      openshift_redirect_uri = "https://oauth-openshift.apps.moc-infra.massopen.cloud/oauth2callback/mocsso"
      client_secret_name     = "cluster/moc-infra/keycloak-oidc"
      keycloak_client_uuid   = "moc-infra"
    }
    oac_prod_infra = {
      cluster_name           = "oac-prod-infra"
      openshift_redirect_uri = "https://oauth-openshift.apps.infra.oac.ocp.massopen.cloud/oauth2callback/mocsso"
      client_secret_name     = "cluster/oac-prod-infra/keycloak-oidc"
      keycloak_client_uuid   = "oac-prod-infra"
    }
    oac_prod_workload0 = {
      cluster_name           = "oac-prod-workload0"
      openshift_redirect_uri = "https://oauth-oac-prod-workload0.hcp.oac.massopen.cloud:443/oauth2callback/mocsso"
      client_secret_name     = "cluster/oac-prod-infra/hostedcluster/oac-prod-workload0/keycloak-oidc"
      keycloak_client_uuid   = "oac-prod-workload0"
    }
    oac_dev_workload0 = {
      cluster_name           = "oac-dev-workload0"
      openshift_redirect_uri = "https://oauth-oac-dev-workload0.hcp.oac.int.massopen.cloud:443/oauth2callback/mocsso"
      client_secret_name     = "cluster/oac-dev-infra/hostedcluster/oac-dev-workload0/keycloak-oidc"
      keycloak_client_uuid   = "oac-dev-workload0"
    }
    oac_dev_workload1 = {
      cluster_name           = "oac-dev-workload1"
      openshift_redirect_uri = "https://oauth-oac-dev-workload1.hcp.oac.int.massopen.cloud:443/oauth2callback/mocsso"
      client_secret_name     = "cluster/oac-dev-infra/hostedcluster/oac-dev-workload1/keycloak-oidc"
      keycloak_client_uuid   = "oac-dev-workload1"
    }
    oac_dev_workload2 = {
      cluster_name           = "oac-dev-workload2"
      openshift_redirect_uri = "https://oauth-oac-dev-workload2.hcp.oac.int.massopen.cloud:443/oauth2callback/mocsso"
      client_secret_name     = "cluster/oac-dev-infra/hostedcluster/oac-dev-workload2/keycloak-oidc"
      keycloak_client_uuid   = "oac-dev-workload2"
    }
    nist_dev_workload0 = {
      cluster_name           = "nist-dev-workload0"
      openshift_redirect_uri = "https://oauth-nist-dev-workload0.hcp-int.nist.int.massopen.cloud:443/oauth2callback/mocsso"
      client_secret_name     = "cluster/nist-dev-infra/hostedcluster/nist-dev-workload0/keycloak-oidc"
      keycloak_client_uuid   = "nist-dev-workload0"
    }
    nist_dev_infra = {
      cluster_name           = "nist-dev-infra"
      openshift_redirect_uri = "https://oauth-openshift.apps.nist-dev-infra.nist.int.massopen.cloud/oauth2callback/mocsso"
      client_secret_name     = "cluster/nist-dev-infra/keycloak-oidc"
      keycloak_client_uuid   = "nist-dev-infra"
    }
    compliant_dev_infra = {
      cluster_name           = "compliant-dev-infra"
      openshift_redirect_uri = "https://oauth-openshift.apps.compliant-dev-infra.nist.int.massopen.cloud/oauth2callback/mocsso"
      client_secret_name     = "cluster/compliant-dev-infra/keycloak-oidc"
      keycloak_client_uuid   = "compliant-dev-infra"
    }
    compliant_dev_workload0 = {
      cluster_name           = "compliant-dev-workload0"
      openshift_redirect_uri = "https://oauth-compliant-dev-workload0.hcp-int.nist.int.massopen.cloud:443/oauth2callback/mocsso"
      client_secret_name     = "cluster/compliant-dev-infra/hostedcluster/compliant-dev-workload0/keycloak-oidc"
      keycloak_client_uuid   = "compliant-dev-workload0"
    }
    bu_ist_demo_infra = {
      cluster_name           = "bu-ist-demo-infra"
      openshift_redirect_uri = "https://oauth-openshift.apps.bu-ist-demo.int.massopen.cloud/oauth2callback/mocsso"
      client_secret_name     = "cluster/bu-ist-demo-infra/keycloak-oidc"
      keycloak_client_uuid   = "bu-ist-demo-infra"
    }
  }
}

module "openshift_oidc" {
  for_each = local.openshift_oidc_clusters

  source                 = "./modules/openshift-oidc"
  cluster_name           = each.value.cluster_name
  openshift_redirect_uri = each.value.openshift_redirect_uri
  client_secret_name     = each.value.client_secret_name
  realm_id               = keycloak_realm.moc.id
  use_secrets_manager    = var.use_secrets_manager
  additional_scope_names = [keycloak_openid_client_scope.groups.name, keycloak_openid_client_scope.openid.name]
}
