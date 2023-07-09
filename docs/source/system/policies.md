# Policies

## Shared Attributes

All policies have either a target/requirement or an input price.

.. autopydantic_model:: new_modeling_toolkit.common.policy.Policy
    :model-show-json: False
    :model-show-config-summary: False
    :model-show-config-member: False
    :model-show-field-summary: False
    :model-show-validator-summary: False
    :model-show-validator-members: False
    :field-list-validators: False

### Target, Target Units & Target Adjustment
```{eval-rst}

.. autopydantic_field:: new_modeling_toolkit.common.policy.Policy.target
    :field-list-validators: False
    
.. autopydantic_field:: new_modeling_toolkit.common.policy.Policy.target_adjustment
    :field-list-validators: False
    
.. autopydantic_field:: new_modeling_toolkit.common.policy.Policy.target_units
    :field-list-validators: False

```

### Price
```{eval-rst}
.. autopydantic_field:: new_modeling_toolkit.common.policy.Policy.price
    :field-list-validators: False

```

## Annual Emissions Policies 

## Annual Energy Standard

(RPS, CES, etc.)

## Planning Reserve Margin