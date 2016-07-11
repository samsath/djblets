"""Base support and standard operators for condition choices."""

from __future__ import unicode_literals

from django.utils.translation import ugettext_lazy as _

from djblets.conditions.errors import (ConditionOperatorConflictError,
                                       ConditionOperatorNotFoundError)
from djblets.registries.registry import (ALREADY_REGISTERED,
                                         ATTRIBUTE_REGISTERED, DEFAULT_ERRORS,
                                         NOT_REGISTERED, OrderedRegistry,
                                         UNREGISTER)


class BaseConditionOperator(object):
    """Base class for an operator for a condition choice.

    An operator forms an expression along with a parent
    :py:class:`~djblets.conditions.choices.BaseConditionChoice` and an optional
    value. This expression can be used by the condition to determine if a
    caller-provided value satisfies the condition.

    Choices will usually have more than one operator registered. Depending on
    the operator, there may or may not be a field for a value.

    Attributes:
        choice (djblets.conditions.choices.BaseConditionChoice):
            The choice owning the instance of this operation.
    """

    #: The ID of the operator.
    #:
    #: This must be unique within a
    #: :py:class:`~djblets.conditions.choices.BaseConditionChoice`.
    operator_id = None

    #: The displayed name for the operator.
    name = None

    def __init__(self, choice):
        """Initialize the operator.

        Args:
            choice (djblets.conditions.choices.BaseConditionChoice):
                The choice owning the instance of this operator.
        """
        self.choice = choice

    @property
    def value_field(self):
        """The field type used to prompt and render fields.

        By default, this will use the default one for the choice. The field
        can be disabled by setting this to ``None``, or a different field can
        be used by setting it to an instance of a
        :py:class:`~djblets.conditions.values.BaseConditionValueField`
        subclass.
        """
        return self.choice.default_value_field

    @property
    def has_custom_value_field(self):
        """Whether the operator has a custom value field."""
        return self.value_field is not self.choice.default_value_field

    def matches(self, lookup_value, stored_value):
        """Return whether a value matches the operator and condition's value.

        This must be implemented by subclasses.

        Args:
            lookup_value (object):
                The caller's value to check against the state for this
                operator.

            condition_value (object):
                The value stored as part of the condition to check against.
                This will only be used if the operator has a value field
                associated.

        Returns:
            bool:
            ``True`` if the lookup value fulfills the condition. ``False`` if
            it does not.

        Raises:
            TypeError:
                Either the lookup or condition value or types was not
                compatible with the expression.
        """
        raise NotImplementedError


class OneOfOperator(BaseConditionOperator):
    """An operator that matches against a set of possible values.

    This operator checks if the lookup value matches one of a set of possible
    values listed in the condition.

    This is equivalent to::

        if lookup_value in condition_value:
            ...
    """

    operator_id = 'one-of'
    name = _('Is one of')

    def matches(self, lookup_value, condition_value):
        """Return whether the lookup value has a boolean or truthy value.

        Args:
            lookup_value (object):
                The caller's value to check against the state for this
                operator.

            condition_value (list):
                A list of possible values that the lookup value must match.

        Returns:
            bool:
            ``True`` if the lookup value is present in the list of possible
            values.

        Raises:
            TypeError:
                Either the lookup or condition value was not compatible with
                the expression.
        """
        return lookup_value in condition_value


class AnyOperator(BaseConditionOperator):
    """An operator that matches for any non-empty/zero value.

    This operator checks if the lookup value provided is a non-empty value
    (a boolean, integer, string/list/dictionary containing a value, etc.).
    To determine if the value is empty, the operator checks ``len(value)``.
    If not 0, or if the value doesn't support a length check, it's assumed
    to have a value.

    This is equivalent to::

        if lookup_value in (0, False) or bool(lookup_value):
            ...

    The operator does not accept a user-provided condition value.

    This is the opposite of :py:class:`UnsetOperator`.
    """

    operator_id = 'any'
    name = _('Has a value')
    value_field = None

    def matches(self, lookup_value, condition_value):
        """Return whether the lookup value is non-empty.

        Args:
            lookup_value (object):
                The caller's value to check against the state for this
                operator.

            condition_value (object):
                Unused.

        Returns:
            bool:
            ``True`` if the value is evaluated as not empty.
            ``False`` if it evalutes as empty.
        """
        return lookup_value in (0, False) or bool(lookup_value)


class UnsetOperator(BaseConditionOperator):
    """An operator that matches for an unset/empty value.

    This operator checks if the lookup value provided is an empty value (such
    as empty string/list/dictionary or ``None``). This performs a simple
    ``not`` check against the value, but filters out values that evalute to
    ``False`` but are not considered unset.

    This is equivalent to::

        if lookup_value not in (0, False) and not lookup_value:
            ...

    The operator does not accept a user-provided condition value.

    This is the opposite of :py:class:`AnyOperator`.
    """

    operator_id = 'none'
    name = _('Is unset')
    value_field = None

    def matches(self, lookup_value, condition_value):
        """Return whether the lookup value is empty.

        Args:
            lookup_value (object):
                The caller's value to check against the state for this
                operator.

            condition_value (object):
                Unused.

        Returns:
            bool:
            ``True`` if the value is evaluated as empty.
            ``False`` if it evalutes as not empty.
        """
        return lookup_value not in (0, False) and not lookup_value


class IsOperator(BaseConditionOperator):
    """An operator that checks if one value is the same as another.

    This operator checks for equality, comparing the lookup value to the stored
    condition value.

    It's equivalent to::

        if lookup_value == condition_value:
            ...

    This is the opposite of :py:class:`IsNotOperator`.
    """

    operator_id = 'is'
    name = _('Is')

    def matches(self, lookup_value, condition_value):
        """Return whether the lookup value equals a condition value.

        Args:
            lookup_value (object):
                The caller's value to check against the state for this
                operator.

            condition_value (object):
                The value to compare against.

        Returns:
            bool:
            ``True`` if the lookup value equals the condition value.
        """
        return lookup_value == condition_value


class IsNotOperator(BaseConditionOperator):
    """An operator that checks if one value is not the same as another.

    This operator checks for inequality, comparing the lookup value to the
    stored condition value.

    It's equivalent to::

        if lookup_value != condition_value:
            ...

    This is the opposite of :py:class:`IsOperator`.
    """

    operator_id = 'is-not'
    name = _('Is not')

    def matches(self, lookup_value, condition_value):
        """Return whether the lookup value is not equal to a condition value.

        Args:
            lookup_value (object):
                The caller's value to check against the state for this
                operator.

            condition_value (object):
                The value to compare against.

        Returns:
            bool:
            ``True`` if the lookup value is not equal to the condition value.
        """
        return lookup_value != condition_value


class ContainsOperator(BaseConditionOperator):
    """An operator that checks if a lookup value contains a condition value.

    This operator checks if the provided lookup value contains the condition
    value within the value. It's useful for checking if a string or list
    contains some value.

    It's equivalent to::

        if condition_value in lookup_value:
            ...

    This is the opposite of :py:class:`DoesNotContainOperator`.
    """

    operator_id = 'contains'
    name = _('Contains')

    def matches(self, lookup_value, condition_value):
        """Return whether the lookup value contains a condition value.

        Args:
            lookup_value (object):
                The caller's value to check for a condition value within.

            condition_value (object):
                The value to check within the lookup value.

        Returns:
            bool:
            ``True`` if the lookup value contains the condition value.

        Raises:
            TypeError:
                Either the lookup or condition value was not compatible with
                the expression.
        """
        return condition_value in lookup_value


class DoesNotContainOperator(BaseConditionOperator):
    """An operator that checks if a lookup value does not contain a value.

    This operator checks if the provided lookup value does not contain the
    condition value within the value. It's useful for checking if a string
    or list does not contain some value.

    It's equivalent to::

        if condition_value not in lookup_value:
            ...

    This is the opposite of :py:class:`ContainsOperator`.
    """

    operator_id = 'does-not-contain'
    name = _('Does not contain')

    def matches(self, lookup_value, condition_value):
        """Return whether the lookup value does not contain a condition value.

        Args:
            lookup_value (object):
                The caller's value to check for a condition value within.

            condition_value (object):
                The value to check within the lookup value.

        Returns:
            bool:
            ``True`` if the lookup value does not contain the condition value.

        Raises:
            TypeError:
                Either the lookup or condition value was not compatible with
                the expression.
        """
        return condition_value not in lookup_value


class StartsWithOperator(BaseConditionOperator):
    """An operator that checks if a string starts with another string.

    This operator checks if the lookup value (assumed to be a string) starts
    with the condition value (also a string).

    It's equivalent to::

        if lookup_value.startswith(condition_value):
            ...
    """

    operator_id = 'starts-with'
    name = _('Starts with')

    def matches(self, lookup_value, condition_value):
        """Return whether the lookup value starts with the condition value.

        Args:
            lookup_value (unicode):
                The caller's value to check.

            condition_value (unicode):
                The value to check at the start of the lookup value string.

        Returns:
            bool:
            ``True`` if the lookup value starts with the condition value.

        Raises:
            TypeError:
                Either the lookup or condition value was not a string (or
                string-like object).
        """
        try:
            return lookup_value.startswith(condition_value)
        except AttributeError:
            raise TypeError(
                _('Lookup value %r does not support startswith()'))


class EndsWithOperator(BaseConditionOperator):
    """An operator that checks if a string ends with another string.

    This operator checks if the lookup value (assumed to be a string) ends
    with the condition value (also a string).

    It's equivalent to::

        if lookup_value.endswith(condition_value):
            ...
    """

    operator_id = 'ends-with'
    name = _('Ends with')

    def matches(self, lookup_value, condition_value):
        """Return whether the lookup value ends with the condition value.

        Args:
            lookup_value (unicode):
                The caller's value to check.

            condition_value (unicode):
                The value to check at the end of the lookup value string.

        Returns:
            bool:
            ``True`` if the lookup value ends with the condition value.

        Raises:
            TypeError:
                Either the lookup or condition value was not a string (or
                string-like object).
        """
        try:
            return lookup_value.endswith(condition_value)
        except AttributeError:
            raise TypeError(
                _('Lookup value %r does not support startswith()'))


class GreaterThanOperator(BaseConditionOperator):
    """An operator that checks if a number is greater than a value.

    This operator checks if the lookup value (assumed to be an integer or
    similar) is greater than the condition value.

    It's equivalent to::

        if lookup_value > condition_value:
            ...
    """

    operator_id = 'greater-than'
    name = _('Greater than')

    def matches(self, lookup_value, condition_value):
        """Return whether the lookup value is greater than the condition value.

        Args:
            lookup_value (object):
                The caller's value to check.

            condition_value (object):
                The value that the lookup value must be greater than.

        Returns:
            bool:
            ``True`` if the lookup value is greater than the condition value.
        """
        return lookup_value > condition_value


class LessThanOperator(BaseConditionOperator):
    """An operator that checks if a number is less than a value.

    This operator checks if the lookup value (assumed to be an integer or
    similar) is less than the condition value.

    It's equivalent to::

        if lookup_value < condition_value:
            ...
    """

    operator_id = 'less-than'
    name = _('Less than')

    def matches(self, lookup_value, condition_value):
        """Return whether the lookup value is less than the condition value.

        Args:
            lookup_value (object):
                The caller's value to check.

            condition_value (object):
                The value that the lookup value must be less than.

        Returns:
            bool:
            ``True`` if the lookup value is less than the condition value.
        """
        return lookup_value < condition_value


class ConditionOperators(OrderedRegistry):
    """Represents a list of operators for a condition choice.

    This stores a list of operators that can be used for condition choices.
    It can be used in one of two ways:

    1. Created dynamically, taking a list of :py:class:`BaseConditionOperator`
       subclasses as arguments.
    2. Subclassed, with :py:attr:`operator_classes` set to a list of
       :py:class:`BaseConditionOperator` subclasses.

    This works as a :py:ref:`registry <registry-guides>`, allowing additional
    choices to be added dynamically by extensions or other code.
    """

    #: A list of default operators.
    #:
    #: This is only used if a list of operators is not passed to the
    #: constructor.
    operator_classes = []

    lookup_attrs = ('operator_id',)
    lookup_error_class = ConditionOperatorNotFoundError
    already_registered_error_class = ConditionOperatorConflictError

    default_errors = dict(DEFAULT_ERRORS, **{
        ALREADY_REGISTERED: _(
            'Could not register condition operator %(item)s: This operator is '
            'already registered or its ID conflicts with another operator.'
        ),
        ATTRIBUTE_REGISTERED: _(
            'Could not register condition operator %(item)s: Another operator '
            '%(duplicate)s) is already registered with the same ID.'
        ),
        NOT_REGISTERED: _(
            'No operator was found matching "%(attr_value)s".'
        ),
        UNREGISTER: _(
            'Could not unregister condition operator %(item)s: This condition '
            'was not yet registered.'
        ),
    })

    def __init__(self, operators=[], *args, **kwargs):
        """Initialize the list of operators.

        Args:
            operators (list of type, optional):
                A list of :py:class:`BaseConditionOperator` subclasses. If this
                is provided, any value set for :py:attr:`operator_classes` will
                be ignored.
        """
        super(ConditionOperators, self).__init__(*args, **kwargs)

        self._operators = operators or self.operator_classes

    def get_operator(self, operator_id, choice):
        """Return an operator instance with the given ID.

        Args:
            operator_id (unicode):
                The ID of the operator to retrieve.

            choice (djblets.conditions.choices.BaseConditionChoice):
                The choice that will own this operator instance.

        Returns:
            BaseConditionOperator:
            The operator instance matching the ID.

        Raises:
            djblets.conditions.errors.ConditionOperatorNotFoundError:
                No operator was found that matched the given ID.
        """
        operator_cls = self.get('operator_id', operator_id)

        return operator_cls(choice)

    def get_defaults(self):
        """Return the default operators for the list.

        This is used internally by the parent registry classa, and is based on
        the list of operators provided to the constructor or the value for
        :py:attr:`operator_classes`.

        Returns:
            list of type:
            The default list of operators.
        """
        return self._operators
