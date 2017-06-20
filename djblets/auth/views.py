#
# views.py -- Views for the authentication app
#
# Copyright (c) 2007-2009  Christian Hammond
# Copyright (c) 2007-2009  David Trowbridge
# Copyright (C) 2007 Micah Dowty
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
"""Authentication-related views.

The bundled views help with common authentication-related tasks not otherwise
provided by Django. At the moment, there is only support here for registration.
"""



from django.contrib import auth
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template.context import RequestContext
from django.views.decorators.csrf import csrf_protect

from djblets.auth.forms import RegistrationForm
from djblets.auth.signals import user_registered
from djblets.auth.util import validate_test_cookie


@csrf_protect
def register(request, next_page, form_class=RegistrationForm,
             extra_context=None, initial_values=None,
             form_kwargs=None, template_name="accounts/register.html"):
    """Handle registration of a new user.

    This works along with :py:class:`djblets.auth.forms.RegistrationForm`
    to register a new user. It will display a registration form, validate
    the user's new information, and then log them in.

    The registration form, next page, and context can all be customized by
    the caller.

    Args:
        request (HttpRequest):
            The HTTP request from the client.

        next_page (unicode):
            The URL to navigate to once registration is successful.

        form_class (Form subclass):
            The form that will handle registration, field validation, and
            creation of the user.

        extra_context (dict):
            Extra context variables to pass to the template when rendering.

        initial_values (dict):
            Initial values to set on the form when it is rendered.

        form_kwargs (dict):
            Additional keyword arguments to pass to the form class during
            instantiation.

        template_name (unicode):
            The name of the template containing the registration form.

    Returns:
        HttpResponse: The page's rendered response or redirect.
    """
    if initial_values is None:
        initial_values = {}

    if form_kwargs is None:
        form_kwargs = {}

    if request.method == 'POST':
        form = form_class(data=request.POST, request=request, **form_kwargs)
        form.full_clean()
        validate_test_cookie(form, request)

        if form.is_valid():
            user = form.save()
            if user:
                user = auth.authenticate(
                    username=form.cleaned_data['username'],
                    password=form.cleaned_data['password1'])
                assert user
                auth.login(request, user)
                try:
                    request.session.delete_test_cookie()
                except KeyError:
                    # Do nothing
                    pass

                # Other components can listen to this signal to
                # perform additional tasks when a new user registers
                user_registered.send(sender=None, user=request.user)

                return HttpResponseRedirect(next_page)
    else:
        form = form_class(initial=initial_values, request=request,
                          **form_kwargs)

    request.session.set_test_cookie()

    context = {
        'form': form,
    }

    if extra_context:
        context.update(extra_context)

    return render_to_response(template_name, RequestContext(request, context))
