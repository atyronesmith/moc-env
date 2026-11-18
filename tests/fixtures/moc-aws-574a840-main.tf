terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    b2 = {
      source  = "Backblaze/b2"
      version = "~> 0.12"
    }
  }
}

provider "aws" {
  region = "us-east-1"

  # This applies the "managed-by: moc-aws" tag to all resources created by this
  # repository. This is useful in e.g. resource explorer queries to identify
  # unmanaged resources.
  #
  # aws resource-explorer-2 search --query-string='-tag:managed-by=moc-aws'
  default_tags {
    tags = {
      managed-by = "moc-aws"
    }
  }
}

module "github-oidc" {
  source         = "./modules/github-oidc"
  dns_policy_arn = aws_iam_policy.route53_records.arn

  consumer_repos = {
    moc-keycloak = {
      repository         = "CCI-MOC/moc-keycloak"
      state_keys         = ["moc-keycloak"]
      ro_secret_prefixes = ["cluster/moc-services/"]
      rw_secret_prefixes = ["cluster/*/keycloak-oidc"]
      # moc-keycloak's OIDC subject uses GitHub's immutable org/repo IDs, so the
      # default "repo:CCI-MOC/moc-keycloak:*" cannot match. Value obtained with:
      #   gh api repos/CCI-MOC/moc-keycloak/actions/oidc/customization/sub --jq .sub_claim_prefix
      subject_claims = ["repo:CCI-MOC@3578683/moc-keycloak@1352835750:*"]
    }

    moc-github = {
      repository         = "CCI-MOC/moc-github"
      state_keys         = ["moc-github"]
      ro_secret_prefixes = []
      rw_secret_prefixes = []
      subject_claims     = ["repo:CCI-MOC@3578683/moc-github@1382173862:*"]
    }
  }
}

locals {
  # Defaults for every openshift_oidc_clusters entry. Each cluster below is
  # built with merge(local.openshift_oidc_cluster_defaults, { ... }) so that
  # every entry ends up with an identical set of keys. This keeps the map
  # homogeneous, which OpenTofu requires: if entries had differing key sets it
  # would unify them into a single object type and backfill the missing keys as
  # "known after apply", causing a cryptic for_each error downstream.
  #
  # Required keys default to null; the module marks them nullable = false so an
  # omitted required key fails with a clear message naming the cluster. Optional
  # keys default to a usable empty value.
  openshift_oidc_cluster_defaults = {
    cluster_name                 = null # required
    oidc_bucket_domain_name      = null # required
    cert_manager_policy_arn      = null # required
    eso_readable_secret_prefixes = []   # optional
    eso_writable_secret_prefixes = []   # optional
    service_account_roles        = {}   # optional
  }

  openshift_oidc_clusters = {
    dizzy = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "dizzy"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_dizzy"].policy_arn
      eso_readable_secret_prefixes = [
        "cluster/dizzy/",
      ]
      eso_writable_secret_prefixes = [
        "cluster/dizzy/hostedcluster/",
      ]
    })
    oac_infra = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "oac-infra-dev"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_oac_dev_infra"].policy_arn
      eso_readable_secret_prefixes = [
        "cluster/oac-dev-infra/",
      ]
      eso_writable_secret_prefixes = [
        "cluster/oac-infra-dev/hostedcluster/",
        "cluster/oac-dev-infra/hostedcluster/",
        "cluster/common/object-storage-proxy/certificate",
      ]
      service_account_roles = {
        object-storage-certificate = {
          namespace       = "object-storage-certificate"
          service_account = "object-storage-certificate"
          policy_arns     = [module.cert_manager_policy["cert_manager_policy_storage_massopen"].policy_arn]
        }
      }
    })
    oac_dev_workload0 = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "oac-dev-workload0"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_oac_dev_workload0"].policy_arn
    })
    oac_dev_workload1 = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "oac-dev-workload1"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_oac_dev_workload1"].policy_arn
    })
    oac_dev_workload2 = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "oac-dev-workload2"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_oac_dev_workload2"].policy_arn
    })
    # Standalone spoke of oac-dev-infra; hosts GPU VMs for its hosted clusters.
    jetty = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "jetty"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_jetty"].policy_arn
    })
    oac_prod_infra = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "oac-prod-infra"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_oac_prod_infra"].policy_arn
      eso_readable_secret_prefixes = [
        "b2-key/oac-prod-workload0-rw",
        "b2-key/oac-prod-workload0-ro",
        "b2-key/oac-invoicing-rw",
      ]
      eso_writable_secret_prefixes = [
        "cluster/oac-prod-infra/hostedcluster/",
      ]
    })
    oac_prod_workload0 = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "oac-prod-workload0"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_oac_prod_workload0"].policy_arn
    })
    nist_dev_infra = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "nist-dev-infra"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_nist_dev_infra"].policy_arn
      # external-dns reads its access key where the iam-user module stores it.
      eso_readable_secret_prefixes = [
        "iam-user/nist-dev-external-dns/",
      ]
      # HyperShift's kubeconfig and etcd encryption key for each hosted cluster.
      eso_writable_secret_prefixes = [
        "cluster/nist-dev-infra/hostedcluster/",
      ]
    })
    nist_dev_workload0 = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "nist-dev-workload0"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_nist_dev_workload0"].policy_arn
    })
    compliant_dev_infra = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "compliant-dev-infra"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_compliant_dev_infra"].policy_arn
      # external-dns reads its access key where the iam-user module stores it.
      eso_readable_secret_prefixes = [
        "iam-user/nist-dev-external-dns/",
      ]
      # HyperShift's kubeconfig and etcd encryption key for each hosted cluster.
      eso_writable_secret_prefixes = [
        "cluster/compliant-dev-infra/hostedcluster/",
      ]
    })
    compliant_dev_workload0 = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "compliant-dev-workload0"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_compliant_dev_workload0"].policy_arn
    })
    # Standalone MOC cluster managed by CCI-MOC/moc-infra-config.
    moc_infra = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "moc-infra"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_moc_infra_massopen"].policy_arn
    })
    bu_ist_demo_infra = merge(local.openshift_oidc_cluster_defaults, {
      cluster_name            = "bu-ist-demo-infra"
      oidc_bucket_domain_name = aws_s3_bucket.oac_oidc.bucket_regional_domain_name
      cert_manager_policy_arn = module.cert_manager_policy["cert_manager_policy_bu_ist_demo_infra"].policy_arn
      # external-dns reads its access key where the iam-user module stores it.
      eso_readable_secret_prefixes = [
        "iam-user/bu-ist-demo-infra-external-dns/",
      ]
    })
  }
}

module "openshift_oidc" {
  for_each = local.openshift_oidc_clusters

  source                       = "./modules/openshift-oidc"
  cluster_name                 = each.value.cluster_name
  oidc_bucket_domain_name      = each.value.oidc_bucket_domain_name
  cert_manager_policy_arn      = each.value.cert_manager_policy_arn
  eso_readable_secret_prefixes = each.value.eso_readable_secret_prefixes
  eso_writable_secret_prefixes = each.value.eso_writable_secret_prefixes
  service_account_roles        = each.value.service_account_roles
}

module "wasabi" {
  source = "./wasabi"

  wasabi_access_key = var.wasabi_access_key
  wasabi_secret_key = var.wasabi_secret_key

  providers = {
    aws = aws
  }
}

module "b2" {
  source = "./b2"

  b2_access_key = var.b2_access_key
  b2_secret_key = var.b2_secret_key

  providers = {
    aws = aws
  }
}
